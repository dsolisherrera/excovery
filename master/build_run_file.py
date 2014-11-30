########################################################################################################################
#This file is responsible for creating the run_file.xml file which is used as a log for the runs 
#This file is used  when the the run_file is missing or corrupted 
########################################################################################################################

from Master_EventHandler import EventHandler
import optparse
import os
import sys
import time
import xml.dom.minidom as dom
from xml.dom import Node
import xmlrpclib
import subprocess
import datetime
import threading
from exp_description import *
import random
import Queue
import string
import socket
import shutil
import shlex
import re
import xml.etree.ElementTree as ET
import commands


############################################################
#pretty print function
############################################################

def indent(elem, level=0):
  i = "\n" + level*"  "
  if len(elem):
    if not elem.text or not elem.text.strip():
      elem.text = i + "  "
    if not elem.tail or not elem.tail.strip():
      elem.tail = i
    for elem in elem:
      indent(elem, level+1)
    if not elem.tail or not elem.tail.strip():
      elem.tail = i
  else:
    if level and (not elem.tail or not elem.tail.strip()):
      elem.tail = i


def build_xml_file(experiment_xml_file):
	xml_run_file='run_file.xml';#create a new file only if it doesn't exists
	


	#Create a new experiment_description just to use its methods
	exp_run = experiment_description(experiment_xml_file);
	Exp_Enc_f = open("run_file.xml","w+"); #Open the file for write and overwrite 
	s='<!-- Number of factor = %d -->\n'%len(exp_run.factor_list);
	Exp_Enc_f.write(s);
	s= '<run_list>\n';
	Exp_Enc_f.write(s);
	s= '</run_list>\n';
	Exp_Enc_f.write(s);
	Exp_Enc_f.close();








	# Option parser ############################################################
parser = optparse.OptionParser(
	description='Run Service Discovery Experiments.',
	prog=os.path.basename(sys.argv[0]),
	version='%s 0.0.4' % os.path.basename(sys.argv[0]),
)

parser.add_option('-f', metavar='experiment_description', dest='experiment_description', help='file with description')
parser.add_option('-v', action='store_true', dest='verbose', help='give this option to produce more output')

options, arguments = parser.parse_args()
	

if options.experiment_description==None:
	print 'No xml experiment description file given.';
	exit();

results_dir_name_nodes = "MasterResults";
exp_run = experiment_description(options.experiment_description);
experiment_name = "%s" % exp_run.experiment_name

full_run_matrix =None;
full_run_matrix = [];
factor_level_matrix = None;
factor_level_matrix =[];

for fact in exp_run.factor_list:
	factor_level_matrix.append(fact.levels.get_len());

Master_dir = "%s/%s" % (results_dir_name_nodes, experiment_name) ;
exp_run_dir = os.getcwd();


run_matrix_done =None;
run_matrix_done = [];

if os.path.exists(Master_dir):

	#Fetch element in the results dir by time of creation
	os.chdir(Master_dir);
	a = commands.getstatusoutput("ls -ltr | awk '{print $9}'")
	list  =a[1].split('\n')

	os.chdir(exp_run_dir)



	dircontents_Nodes = os.listdir(Master_dir)
	dirpattern_Nodes  = re.compile("^run_[0-9]+_[0-9]+_[0-9]+_[0-9]+$")		
	
	# Find existing run directories
	for direlement in list:
		run_factor_value_item = None;
		run_factor_value_item = []  ;
		if (options.verbose):
			print direlement;
		if re.match(dirpattern_Nodes, direlement):
			#contruction of run_count value for each run_count
			for i in range(0,len(factor_level_matrix)) :
				run_factor_value_item.insert(i,int(direlement.split("_")[i+1])) ;
			
			run_matrix_done.append(run_factor_value_item);


for run_done in run_matrix_done:
	if (options.verbose):
		print run_done;



#Build the xml file

build_xml_file(options.experiment_description);





#Create the full matrix
full_run_matrix = exp_run.get_run_matrix();


tree = ET.parse('run_file.xml');
root = tree.getroot();

#Search for each item in the run_matrix to obtain its location
for value_index in range(0,len(run_matrix_done)):
	for full_matrix_index in range (0,len(full_run_matrix)):
		if(run_matrix_done[value_index] == full_run_matrix[full_matrix_index]):
			if (options.verbose):
				print full_matrix_index;
			#Build the run_node	
		  	run_done=ET.Element("run_done",run_matrix_value = str(full_matrix_index),value=str(value_index));
  			root.append(run_done);
  			#tree.write('run_file.xml');
  			#build the factor node
  			i=0;
			for factor in exp_run.factor_list:
				i =i+1;
				run_factor=ET.Element("factor",id=str(factor.id),size=str(factor.levels.get_len()),index=str(i),value=str(full_run_matrix[full_matrix_index][i-1]));
				run_done.append(run_factor);
  			break;


tree.write('run_file.xml');



tree = ET.parse('run_file.xml');
root = tree.getroot();

indent(root);
tree.write('run_file.xml');











