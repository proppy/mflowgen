#=========================================================================
# CtrlReg.py
#=========================================================================
# This module contains control registers that can be read or written with
# a val/rdy interface. Each control register also has an output port from
# this module. The block diagram of the control register design looks like
# this:
#
#            CtrlReg
#           +----------------------------------+
#           |            registers             |
#           | -----+      +----+               |
#     req ->| in_q |----> |    |               |
#           | -----+  |   |    |--+----------> | -> wires out
#           |         |   +/\--+  | data       |
#           |         |           |            |
#           |         |           v    ------+ |
#           |         +--------------> out_q | | -> resp
#           |                          ------+ |
#           |                                  |
#           +----------------------------------+
#
# Request messages go into the input queue. The message is popped out of
# the input queue, and then the read/write happens. For writes, the
# control register is enabled and written, with changes visible on
# the following cycle. For reads, the data for the specified register is
# combinationallly read and then wrapped into the response message.
#
# Response messages go into the output queue. The data field of the
# response message is 0 for writes and has the read data for reads.
#
# Control registers are connected directly to outputs as ports so that
# they can be hooked up to control other parts of the design.
#
# Currently we have these control registers (CRs):
#
# - CR0 (r/w) : go bit, unfreezes the processor
# - CR1 (r/w) : debug bit
# - CR2 (r  ) : number of committed instructions
# - CR3 (r  ) : number of cycles
# - CR4 (r  ) : host enable for MDU
# - CR5 (r  ) : host enable for iCache
# - CR6 (r  ) : host enable for dCache

from pymtl      import *
from pclib.ifcs import InValRdyBundle, OutValRdyBundle
from pclib.rtl  import SingleElementNormalQueue, RegEnRst

from ifcs       import CtrlRegReqMsg, CtrlRegRespMsg

class CtrlReg( Model ):

  def __init__( s, num_cores, valrdy_ifcs = 3 ):

    #---------------------------------------------------------------------
    # Constants
    #---------------------------------------------------------------------

    num_ctrlregs    = 16
    num_ctrlregs_bw = clog2(num_ctrlregs)

    #---------------------------------------------------------------------
    # Interface
    #---------------------------------------------------------------------

    # Ports to host interface

    s.req  = InValRdyBundle ( CtrlRegReqMsg()  )
    s.resp = OutValRdyBundle( CtrlRegRespMsg() )

    # Ports from processor to CtrlReg

    s.commit_inst = InPort( num_cores )
    s.stats_en    = InPort( 1 )

    # Ports from CtrlReg to processor

    s.go          = OutPort( num_cores )

    # Host enable bits

    s.host_en     = OutPort( valrdy_ifcs )

    # Misc ports

    s.debug       = OutPort( 1 )

    #---------------------------------------------------------------------
    # Params
    #---------------------------------------------------------------------

    addr_width = s.req.msg.addr.nbits
    data_width = s.req.msg.data.nbits

    #---------------------------------------------------------------------
    # Input Queue
    #---------------------------------------------------------------------

    s.in_q = m = SingleElementNormalQueue( CtrlRegReqMsg() )

    # Connect input

    s.connect( s.req, m.enq )

    #---------------------------------------------------------------------
    # Control Registers
    #---------------------------------------------------------------------
    # Note that this is a collection of registers, as opposed to a
    # register file. The reason it is not a register file is that many
    # registers can be updated in parallel. For example, the instruction
    # counter and cycle counter can both be updated in the same cycle.

    # Control register mapping
    #
    # NOTE: Make sure that the go bit is ZERO when coming out of reset!

    cr_go           = 0                           # Go bit
    cr_debug        = 1                           # Debug bit
    cr_instcounter  = 2                           # Base for instruction counter
    cr_cyclecounter = cr_instcounter  + num_cores # Base for Cycle counter
    cr_host_en      = cr_cyclecounter + num_cores # Base for Host Enable counter

    # Instantiate registers (16 registers)

    s.ctrlregs = \
      [ RegEnRst( dtype = 32, reset_value = 0 ) for _ in xrange(num_ctrlregs) ]

    # Read interface

    s.rf_raddr = Wire( addr_width )
    s.rf_rdata = Wire( data_width )

    @s.combinational
    def comb_rf_read_interface():
      s.rf_raddr.value = s.in_q.deq.msg.addr
      s.rf_rdata.value = s.ctrlregs[ s.rf_raddr ].out

    # Write interface

    s.rf_wen   = Wire( 1 )
    s.rf_waddr = Wire( addr_width )
    s.rf_wdata = Wire( data_width )

    @s.combinational
    def comb_rf_write_interface():
      s.rf_waddr.value = s.in_q.deq.msg.addr
      s.rf_wdata.value = s.in_q.deq.msg.data
      s.rf_wen.value   = s.in_q.deq.val & \
          ( s.in_q.deq.msg.type_ == CtrlRegReqMsg.TYPE_WRITE )

    # Control Register: Go

    s.cr_go_en = Wire( 1 )
    s.cr_go_in = Wire( 32 )

    @s.combinational
    def comb_cr_go_logic():
      s.cr_go_en.value = s.rf_wen & ( s.rf_waddr == cr_go )
      s.cr_go_in.value = s.rf_wdata

    # Control Register: Debug

    s.cr_debug_en = Wire( 1 )
    s.cr_debug_in = Wire( 32 )

    @s.combinational
    def comb_cr_debug_logic():
      s.cr_debug_en.value = s.rf_wen & ( s.rf_waddr == cr_debug )
      s.cr_debug_in.value = s.rf_wdata

    s.connect_pairs(
      s.ctrlregs[cr_debug].en,  s.cr_debug_en,
      s.ctrlregs[cr_debug].in_, s.cr_debug_in,
    )

    # Control Registers: Instruction counters

    s.instcounters_en  = Wire             ( num_cores )
    s.instcounters_in  = Wire[ num_cores ](    32     )
    s.instcounters_out = Wire[ num_cores ](    32     )

    @s.combinational
    def comb_cr_instcounter_logic():
      for core_idx in xrange(num_cores):
        s.instcounters_en[core_idx].value = s.commit_inst[core_idx] & s.stats_en
        s.instcounters_in[core_idx].value = s.instcounters_out[core_idx] + 1

    #for reg_idx in xrange(cr_instcounter, cr_instcounter + num_cores):
    for reg_idx in xrange(2, 2 + 4):
      core_idx = reg_idx - cr_instcounter
      s.connect_pairs(
        s.ctrlregs        [reg_idx ].in_, s.instcounters_in[core_idx]    ,
        s.ctrlregs        [reg_idx ].en , s.instcounters_en[core_idx]    ,
        s.instcounters_out[core_idx]    , s.ctrlregs       [reg_idx ].out,
      )

    # Control Register: Cycle counters

    s.cyclecounters_en  = Wire             ( num_cores )
    s.cyclecounters_in  = Wire[ num_cores ](    32     )
    s.cyclecounters_out = Wire[ num_cores ](    32     )

    @s.combinational
    def comb_cr_cyclecounter_logic():
      for core_idx in xrange(num_cores):
        s.cyclecounters_en[core_idx].value = s.stats_en
        s.cyclecounters_in[core_idx].value = s.cyclecounters_out[core_idx] + 1

    # Host_en

    s.wire_host_en      = Wire( valrdy_ifcs )

    @s.combinational
    def comb_cr_hosten_logic():
      for idx in xrange(valrdy_ifcs):
        s.wire_host_en[idx].value = s.rf_wen & ( s.rf_waddr == ( idx + cr_host_en ) )

    # Connect write value

    # Instacounters
    cr_instcounter_l  = cr_instcounter
    cr_instcounter_h  = cr_instcounter  + num_cores

    cr_cyclecounter_l = cr_cyclecounter
    cr_cyclecounter_h = cr_cyclecounter + num_cores

    cr_host_en_l      = cr_host_en
    cr_host_en_h      = cr_host_en + valrdy_ifcs

    for ridx in xrange( num_ctrlregs ):

      if   ridx == cr_go:
        s.connect_pairs(
          s.ctrlregs[ridx].in_, s.cr_go_in,
          s.ctrlregs[ridx].en , s.cr_go_en,
        )

        # Go bit is a special case
        # Shunning: currently we set the go bit of all cores at the same time
        for i in xrange(num_cores):
          s.connect_pairs(
            s.go[i], s.ctrlregs[cr_go].out[0],
          )

      elif ridx == cr_debug:
        # debug bit (1 bit)
        s.connect_pairs(
          s.ctrlregs[ridx].in_, s.cr_debug_in             ,
          s.ctrlregs[ridx].en , s.cr_debug_en             ,
          s.debug             , s.ctrlregs   [ridx].out[0],
        )

      elif ridx >= cr_instcounter_l and ridx < cr_instcounter_h:
        cidx = ridx - cr_instcounter
        s.connect_pairs(
          s.ctrlregs        [ridx].in_, s.instcounters_in[cidx]    ,
          s.ctrlregs        [ridx].en , s.instcounters_en[cidx]    ,
          s.instcounters_out[cidx]    , s.ctrlregs       [ridx].out,
        )

      elif ridx >= cr_cyclecounter_l and ridx < cr_cyclecounter_h:
        cidx = ridx - cr_cyclecounter
        s.connect_pairs(
          s.ctrlregs         [ridx].in_, s.cyclecounters_in[cidx]    ,
          s.ctrlregs         [ridx].en , s.cyclecounters_en[cidx]    ,
          s.cyclecounters_out[cidx]    , s.ctrlregs        [ridx].out,
        )

      elif ridx >= cr_host_en_l and ridx < cr_host_en_h:
        cidx = ridx - cr_host_en
        s.connect_pairs(
          s.ctrlregs         [ridx].in_, s.rf_wdata          ,
          s.ctrlregs         [ridx].en , s.wire_host_en[cidx],
        )

    #---------------------------------------------------------------------
    # Output Queue
    #---------------------------------------------------------------------

    s.out_q = m = SingleElementNormalQueue( CtrlRegRespMsg() )

    s.connect( s.in_q.deq.val, m.enq.val )
    s.connect( s.in_q.deq.rdy, m.enq.rdy )

    # Create response message

    @s.combinational
    def comb_resp_msg():
      s.out_q.enq.msg.type_.value  = s.in_q.deq.msg.type_

      if s.in_q.deq.msg.type_ == CtrlRegReqMsg.TYPE_WRITE:
        s.out_q.enq.msg.data.value = 0
      else:
        s.out_q.enq.msg.data.value = s.rf_rdata

    # Connect output

    s.connect( s.out_q.deq, s.resp )

  def line_trace( s ):
    return '({})'.format(s.in_q.deq)
