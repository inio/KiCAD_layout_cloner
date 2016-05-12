#!/usr/bin/env python

#Script for KiCAD Pcbnew to clone a part of a layout. The scipt clones a row or a matrce
#of similar layouts.
#
#For now, there are no command line parameters given for the script, instead
#all the settings are written in this file. Before using this script, you must have your schema
#ready.
#1. Use hierarchical sheets for the subschemas to be cloned and annotate them 
#so that each sheet has module references starting with a different hundred.
#2. Import a netlist into Pcbnew and place all the components except the ones to be cloned.
#3. In the same board file, create also an optimal layout for the subschema to be used
#as the template for the clones.
#4. Surround the layout of the subchema with a zone in the comment layer.
#5. Save the .kicad_pcb file and run this script.
#
#The script has three main parts:
#First, the script moves the modules, which are already imported into the board file. They are
#moved by a predetermined offset amount compared to the template module. (A module with the same
#reference, except starting with a different hundred, eg. templatemodule = D201, clones = D301, D401, D501 etc.)
#Second, the script clones the zones inside the comment layer zone. It seems the zone to be cloned must
#be completely inside the comment zone. Zones have a net defined for them. The script searches for any
#pads inside the cloned zone and sets their net for the zone. So you may get a wrong zone for the net if
#there are pads with different nets inside the zone.
#Third, the script clones the tracks inside the comment zone. Any track touching the zone will be cloned.
#Tracks do not have nets defined for them so they should connect nicely to the modules they will be touching
#after the cloning process.
#
#This script has been tested with KiCAD version BZR 5382 with all scripting settings turned on. (Ubuntu and Python 2.7.6)
#The script can be run in Linux terminal with command $python pcbnew_cloner.py


import sys			
import re			#regexp
import pcbnew

from pcbnew import FromMM
from pcbnew import wxPoint

#Settings, modify these to suit your project

templateRefModulo = 100;  #Difference in the reference numbers between hierarchical sheet
templateRefStart = 200;   #Starting point of numbering in the first hierarchical sheet
move_dx = FromMM(20)      #Spacing between clones in x direction
move_dy = FromMM(0)       #Spacing between clones in y direction
clonesX = 4               #Number of clones in x direction
clonesY = 1               #Number of clones in y direction


def do_clone(templateRefStart, templateRefModulo, clonesX, clonesY, move_dx, move_dy):
  board = pcbnew.GetBoard()
  
  numberOfClones = clonesX * clonesY

  #Cloning zones inside the template area.
  #First lets use the comment zone to define the area to be cloned.
  templateRect = None
  for i in range(0, board.GetAreaCount()):
    zone = board.GetArea(i)				
    if zone.GetLayer() == 41:
      assert templateRect is None, "You must only have one comment zone"
      templateRect = zone.GetBoundingBox()
  print 'Comment zone left top: ', templateRect.GetOrigin(), ' width: ', templateRect.GetWidth(), ' height: ', templateRect.GetHeight()

  modulesToClone = []
  
  netNames = {}
    
  netmap = {}

  # Identify the source modules
  for module in board.GetModules():
      [prefix, index] = re.match('([A-Za-z]+)([0-9]+)',module.GetReference()).groups()
      index = int(index)
      if not templateRect.Contains(module.GetPosition()):
          if index >= templateRefStart and index < templateRefStart+templateRefModulo:
              print 'WARNING: Module in clone range ', module.GetReference(), ' not in clone zone'
      else:
          if index < templateRefStart or index >= templateRefStart+templateRefModulo:
              print 'ERROR: Unexpected module ', module.GetReference(), ' found in clone zone'
          modulesToClone.append((prefix, index))

  # Figure out the mapping between template nets and clone nets.  Use a voting based
  # approach to allow small differences in the netlist structures (e.g. to have ID pins
  # pulled differently).
  for i in range(1, numberOfClones):
      netVotes = {}
      for (referencePrefix, templateReferenceNumber) in modulesToClone:
          templateRef = '%s%d'%(referencePrefix, templateReferenceNumber)
          templateModule = board.FindModuleByReference(templateRef)
          
          cloneRefNumber = templateReferenceNumber + i*templateRefModulo
          cloneRef = '%s%d'%(referencePrefix, cloneRefNumber)

          cloneModule = board.FindModuleByReference(cloneRef)				
          if cloneModule is None:
              print 'Clone module ', cloneRef, ' is not placed in the board.'
              return
          
          if (cloneModule.GetFPID() != templateModule.GetFPID()):
              print 'Clone module ', cloneRef, ' has a different footprint.'
              return

          for (templatePad, clonePad) in zip(templateModule.Pads(), cloneModule.Pads()):
              assert templatePad.GetPadName() == clonePad.GetPadName()
              templateCode = templatePad.GetNetCode()
              cloneCode = clonePad.GetNetCode()
              netVotes.setdefault(templateCode, {})
              netVotes[templateCode].setdefault(cloneCode, 0)
              netVotes[templateCode][cloneCode] += 1
              if templateCode not in netNames:
                netNames[templateCode] = templatePad.GetNetname()
              if cloneCode not in netNames:
                netNames[cloneCode] = clonePad.GetNetname()
              
      for templateCode in netVotes:
          votes = netVotes[templateCode]
          if len(votes) > 1:
            print "non-unanimous net association: %s (clone %d)"%(netNames[templateCode], i)
            for cloneCode in votes:
              print "%8d: %s"%(votes[cloneCode], netNames[cloneCode])
          netmap.setdefault(templateCode, [None]*(numberOfClones+1));
          netmap[templateCode][i] = max(votes, key=votes.get)


  for (referencePrefix, templateReferenceNumber) in modulesToClone:  #For each module in the template zone
      templateRef = '%s%d'%(referencePrefix, templateReferenceNumber)
      templateModule = board.FindModuleByReference(templateRef)  #Find the corresponding module in the input board
      templatePosition = templateModule.GetPosition()
      templateRefText = templateModule.Reference()
      templateValText = templateModule.Reference()
      for i in range(1, numberOfClones):
          cloneRefNumber = templateReferenceNumber + i*templateRefModulo  #Number of the next clone
          cloneRef = '%s%d'%(referencePrefix, cloneRefNumber)  #String reference of the next clone			

          cloneModule = board.FindModuleByReference(cloneRef)				
          if cloneModule is None:
              print 'Module to be moved (', cloneRef, ') is not found in the board.'
              continue
        
          if cloneModule.GetLayer() is not templateModule.GetLayer():			#If the cloned module is not on the same layer as the template
              cloneModule.Flip(wxPoint(1,1))						#Flip it around any point to change the layer
        
          vect = wxPoint(templatePosition.x+(i%clonesX)*move_dx, templatePosition.y+(i//clonesX)*move_dy) #Calculate new position
          cloneModule.SetPosition(vect)						#Set position
          cloneModule.SetOrientation(templateModule.GetOrientation())			#And copy orientation from template
          
          for (templateText, cloneText) in [(templateRefText, cloneModule.Reference()), 
                                            (templateValText, cloneModule.Value())]:
            cloneText.SetPos0(templateText.GetPos0())
            cloneText.SetOrientation(templateText.GetOrientation())
            cloneText.SetHeight(templateText.GetHeight())
            cloneText.SetWidth(templateText.GetWidth())
            cloneText.SetThickness(templateText.GetThickness())
            cloneText.SetVisible(templateText.IsVisible())
  print 'Modules and module text moved and oriented according to template.'

  for templateZoneNum in range(0, board.GetAreaCount()):						#For all the zones in the template board
      zone = board.GetArea(templateZoneNum)
      #print 'Original zone location', zone.GetPosition()
      templateNetCode = zone.GetNetCode()
      if templateRect.Contains(zone.GetPosition()) and zone.GetLayer() is not 41:		#If the zone is inside the area to be cloned (the comment zone) and it is not the comment zone (layer 41)     
          for i in range(1, numberOfClones):						#For each target clone areas
              zoneClone = zone.Duplicate()						#Make copy of the zone to be cloned
              zoneClone.Move(wxPoint(i%clonesX*move_dx, i//clonesX*move_dy))		#Move it inside the target clone area
              if templateNetCode in netmap:
                zoneClone.SetNetCode(netmap[templateNetCode][i]);
              else:
                print 'WARNING: Unknown track net ', track.GetNetname(), ' found in template'
              board.Add(zoneClone)								#Add to the zone board
  print 'Zones cloned.'

  #Cloning tracks inside the template area
  tracks = board.GetTracks()
  cloneTracks = []
  for track in tracks:
      if track.HitTest(templateRect):							#Find tracks which touch the comment zone
          templateNetCode = track.GetNetCode()
          for i in range(1, numberOfClones):						#For each area to be cloned
              cloneTrack = track.Duplicate()						#Copy track
              cloneTrack.Move(wxPoint(i%clonesX*move_dx, i//clonesX*move_dy))		#Move it
              if templateNetCode in netmap:
                cloneTrack.SetNetCode(netmap[templateNetCode][i])
              else:
                print 'WARNING: Unknown track net ', track.GetNetname(), ' found in template'
              cloneTracks.append(cloneTrack)						#Add to temporary list
  for track in cloneTracks:								#Append the temporary list to board
      tracks.Append(track)
  print 'Tracks cloned.'

  #Cloning drawings inside the template area
  drawings = board.GetDrawings()
  cloneDrawings = []
  for drawing in drawings:
      if drawing.HitTest(templateRect):							#Find tracks which touch the comment zone
          for i in range(1, numberOfClones):						#For each area to be cloned
              cloneDrawing = drawing.Duplicate()						#Copy track
              cloneDrawing.Move(wxPoint(i%clonesX*move_dx, i//clonesX*move_dy))		#Move it
              cloneDrawings.append(cloneDrawing)						#Add to temporary list
  for drawing in cloneDrawings:								#Append the temporary list to board
      drawings.Append(drawing)
  print 'Drawings cloned.'

do_clone(templateRefStart, templateRefModulo, clonesX, clonesY, move_dx, move_dy)

print 'Script completed'
