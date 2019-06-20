#! /usr/bin/env python
#=========================================================================
# configure.py
#=========================================================================
#
#  -h --help     Display this message
#  -v --verbose  Verbose mode
#     --design   Name of the design
#
# Author : Christopher Torng
# Date   : June  2, 2019
#

import argparse
import os
import sys

from mflow import BuildOrchestrator
from mflow import MakeBackend, NinjaBackend

#-------------------------------------------------------------------------
# Command line processing
#-------------------------------------------------------------------------

class ArgumentParserWithCustomError(argparse.ArgumentParser):
  def error( self, msg = "" ):
    if ( msg ): print("\n ERROR: %s" % msg)
    print("")
    file = open( sys.argv[0] )
    for ( lineno, line ) in enumerate( file ):
      if ( line[0] != '#' ): sys.exit(msg != "")
      if ( (lineno == 2) or (lineno >= 4) ): print( line[1:].rstrip("\n") )

def parse_cmdline():
  p = ArgumentParserWithCustomError( add_help=False )
  p.add_argument( "-v", "--verbose", action="store_true" )
  p.add_argument( "-h", "--help",    action="store_true" )
  p.add_argument(       "--design",  default="GcdUnit"   )
  p.add_argument(       "--backend", default="make",
                                     choices=("make", "ninja") )
  opts = p.parse_args()
  if opts.help: p.error()
  return opts

#-------------------------------------------------------------------------
# Main
#-------------------------------------------------------------------------

def main():

  opts = parse_cmdline()

  # Check that this design exists

  design_dir = '/'.join([
      os.path.dirname( os.path.abspath( __file__ ) ),
      'designs',
      opts.design,
  ])

  if not os.path.exists( design_dir ):
    raise ValueError(
      'Design "{}" not found at "{}"'.format( opts.design, design_dir ) )

  # Import the graph for this design

  sys.path.append( design_dir  )

  from setup_graph import setup_graph

  # Select the backend

  if opts.backend == 'make':
    backend_cls = MakeBackend
  elif opts.backend == 'ninja':
    backend_cls = NinjaBackend

  # Generate the ninja build

  g = setup_graph()
  b = BuildOrchestrator( g, backend_cls )
  b.build()

main()



