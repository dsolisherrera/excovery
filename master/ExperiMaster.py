'''
This is the main program which executes an experiment 
description by communicating with the Node_Managers on
the configured nodes. 

It has	threads.

* The main thread executes the experiment description

* One thread is providing an XMLRPC Server for the Nodes
to sent asynchonous feedback (mainly events) to the master
program. These events are logged and can be used within
the experiment description to have reactive experiments.

The master program has the following command line parameters:

'''

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



def sendmail(subject, msg):
#	p = os.popen('mail andreas.dittrich@usi.ch -s "%s"' % subject, "w")
	p = os.popen('mail solisd@usi.ch -s "%s"' % subject, "w")
#	p = os.popen('mail andreas.dittrich@usi.ch -s "%s" -c manu.john.panicker@usi.ch' % subject, "w")
	p.write("%s" % msg)
	p.close()
	
def error_log(msg):
	global error_log_lock
	global experiment_data
	'''
	This function shall be used to alert the experimenter
	that something important has gone wrong.
	An email can be sent in this case.
	
	Thread safe
	'''
	error_log_lock.acquire()
	# logfile
	f = "%s/ExperiMasterErrors.log" %experiment_data.get_current_experiment_dir()
	FILE = open(f, "a")
	FILE.write("%s:ERROR " % time.strftime("%y%m%d-%H%M%S",time.localtime()))
	FILE.write("%s " % msg)
	FILE.close()
	error_log_lock.release()
	# email
	sendmail("Error with experiment",msg)
	

def wait_for_threads_or_timeout(thread_list, run_timeout):
	global kill_threads
	kill_threads = 0
	done = False
	while done!=True:
		time.sleep(1)
		run_timeout = run_timeout -1
		if run_timeout % 10==0:
			print "Waiting for run threads to finish (%d)" %(run_timeout)
		if run_timeout==0:
			done=True
		done_count = 0

		for actor_thread in thread_list:
			if actor_thread.is_alive()==False:
				done_count = done_count+1
		if done_count == len(thread_list):
			done=True
			
	kill_threads = 1
	for actor_thread in thread_list:
		if actor_thread.is_alive()==True:
			actor_thread.join()
	  
def do_thread(queue, node, function, arguments):
	r = 0
	try:
		node.lock_node()
		if function=="run_init":
			r=node.run_init(arguments[0], arguments[1])
		elif function=="run_exit":
			r=node.run_exit()
		elif function=="experiment_exit":
			r=node.experiment_exit()
		elif function=="experiment_init":
			r=node.experiment_init(arguments[0],arguments[1],arguments[2],arguments[3])
		elif function=="fail_start_drop_sd":
			r=node.fail_start_drop_sd()
		elif function=="fail_stop_drop_sd":
			r=node.fail_stop_drop_sd()
		elif function=="get_topology":
			r = node.get_topology(arguments[0])
		elif function=="traffic_stop_all":
			r = node.traffic_stop_all()
		elif function=="get_olsr":
			r = node.get_olsr()
		else:
			print "Function not matched %s"%function
			r=-5
			
	except socket.error:
		print "Socket error while trying to exec %s on node %s" %(function, str(node))
		if node.type=="env":
			print "Just an evn node, trying to continue..."
			error_log("Socket error while trying to exec %s on node %s"%(function,str(node)))
			r = -3
		else:
			print "Its an acting node, giving up experiment"
			error_log("Critical:Socket error while trying to exec %s on node ",node %(function))
			r = -2
	except IOError:
		print "Socket IO error, issue retry"
		r = -1
	finally:
		#print "Function:%s" % function
		node.unlock_node()	
		queue.put(r)
		
  
def parallel_exec( nodes, function, *args1):
	'''
	executes requests in parallel and waits for all to return
	returns a list of nodes, that gave a negative result
	'''			
	
	thread_list = []
	queue_list  = []
	failed_list = []
			
	for i in range(len(nodes)):
		queue_list.append(Queue.Queue())
		th = threading.Thread( target=do_thread, kwargs={'queue':queue_list[i], 'node':nodes[i],'function':function, 'arguments': args1} )
		thread_list.append(th)
		#time.sleep(0.15)
		th.daemon = True
		th.start()
	
	for i in range(len(nodes)):
		ret=queue_list[i].get()
		if ret==-1:
			print "parallel_exec returned -1"
			failed_list.append(nodes[i])
		if ret==-2:
			print "parallel_exec returned -2"
			raise Exception
		if ret==-3:
			print "parallel_exec: gave up due to connect to env node"
	
	return failed_list

def wait_for_event_new(waiter_name, event_from, event_type, event_param, start_time=0, timeout=0):
	'''
	@param event_from is a list of nodes (strings), when empty this means "any" or "don't care"
	@param event_param is a list of params (strings)
	'''
	global eh
	global kill_threads
	global verbose
	global simulate
	
	if simulate==True:
		return True
	
	if start_time==0:
		start_time = datetime.datetime.now()
	if timeout!=0:
		end_time = datetime.datetime.now()+datetime.timedelta(seconds=timeout)
		
	wait_result = 1
	eh.event_condition.acquire()
	if len(event_from)==0:
		from_list = list(["any"])
	else:
		from_list = list(event_from)
		
	if len(event_param)==0:
		param_list = list(["any"])
	else:	
		param_list = list(event_param)
	
	dependencies = []
	for e_from in from_list:
		for e_param in param_list:
			dependencies.append( {'from':e_from, 'param':e_param, 'type':event_type} )

	print "%s: Waiting for event %s:" %(waiter_name,event_type)
	while wait_result==1:
		eh.event_condition.wait(5)
		#if verbose:
		#print "%s: Still waiting for %d events" %(waiter_name, len( dependencies))
		for (timestamp_master, node,timestamp,type,param) in eh.event_log:
			removables = []
			for depend in dependencies:
				src_match=0
				type_match=0
				param_match=0
				if depend['from']=="any" or depend['from']==node:
					src_match=1
				if event_type=="any" or event_type==type:
					type_match=1
				if depend['param']=="any" or depend['param']==param or depend['param'].replace("_","")==param: #this is a quirk for the grid10x10
					param_match=1
				
				#print "matches: %d %d %d(%s)" %(src_match, type_match, param_match,type)
				if src_match==1 and type_match==1 and param_match==1:		   
					delta=timestamp_master - start_time
					delay=delta.days*86400*1000+delta.seconds*1000+(delta.microseconds/1000)
					if delay > 0:
						if verbose:
							print "%s: Found new event %s from %s with param %s" %(waiter_name,type,node,param)
						#print "%s: remaing dependencies: " %waiter_name,dependencies
						# yed this is bad, but functionally it works
						dependencies.remove(depend)
						
						if len(dependencies)==0:
							wait_result = 0
						break
		if timeout!=0:
			if datetime.datetime.now() > end_time:
				wait_result = -1
		if kill_threads == 1:
			wait_result = -1
			
	eh.event_condition.release()
	if wait_result==-1:
		return False
	else:
		return True

def wait_wrapper(waiter_name, parameters, exp_wait_marker_time):
	param_dependency="any"
	event_dependency="any"
	instance_dependency="all"
	from_dependency="any"
	timeout=0
	for (name, exp_param) in parameters.items():
		if name=="param_dependency":
			if exp_param.type=="fix":
				param_dependency=exp_param.data
			else:
				param_dependency = exp.get_current_factor_value_by_id(exp_param.data)
				
		if name=="event_dependency":
			if exp_param.type=="fix":
				event_dependency=exp_param.data
			else:
				event_dependency = exp.get_current_factor_value_by_id(exp_param.data)
				
		if name=="from_dependency":
			if exp_param.type=="fix":
				from_dependency=exp_param.data
			else:
				actor_dependency = exp.get_current_factor_value_by_id(exp_param.data)
		if name=="timeout":
			if exp_param.type=="fix":
				timeout=int(exp_param.data)
			else:
				timeout = exp.get_current_factor_value_by_id(exp_param.data)
	# check which node
	map = exp.get_actor_node_map()
	
	from_nodes = []
	param_nodes = []
	#create a list of all nodes (maybe just one)
	if from_dependency!="any":
		from_abstract_nodes = map.get_abstract_nodes(from_dependency["actor"],from_dependency["instance"])
		for an in from_abstract_nodes:
			from_nodes.append(nodeContainer.abstract_node_to_real_node(an).name)
	
	if param_dependency!="any":
		param_abstract_nodes = map.get_abstract_nodes(param_dependency["actor"],param_dependency["instance"])
		for an in param_abstract_nodes:
			param_nodes.append(nodeContainer.abstract_node_to_real_node(an).name)
			
	
	wait_for_event_new(waiter_name,from_nodes,event_dependency, param_nodes, exp_wait_marker_time, timeout)
	
###########################################################################################
######## exp_thread ########################################################
###########################################################################################

class exp_actor_thread(threading.Thread):
	'''
	This class represents the concrete threads.
	Each instance  
	It utilises the actions that are defined by ExperiMaster
	
	This class is also used for the env and the fault threads
	'''
	#exp_wait_marker_time 
	#static exp_description
	exp_description = None
	
	def __init__(self, type, exp_description, id, instance_id, exp_action_list, node):
		'''
		Initialises the thread
		@param type "sd" or "fault"
		@param id the abstract thread identity, given from the xml description
		@param instance_id is the id of the instance of an abstract thread, as given in the xml
		@param node		
		'''
		self.exp_type = type
		self.exp_id = id
		self.exp_instance_id = instance_id
		self.exp_action_list = exp_action_list
		self.exp_node = node
		self.exp_description = exp_description
		self.exp_wait_marker_time = 0
		threading.Thread.__init__(self, name="%s.%s" %(id,instance_id))
					 
	def exp_execute_action(self, action):
		global verbose
		global eh
		global simulate
		
		s = "Thread %s.%s" %(self.exp_id,self.exp_instance_id)
		if action.action=="sd_init":
			if verbose:
				print "%s: sd_init" % s
			self.exp_node.lock_node()
			self.exp_node.SD_init() #change
			self.exp_node.unlock_node()
		if action.action=="sd_exit":
			if verbose:
				print "%s: sd_exit" % s
			self.exp_node.lock_node()
			self.exp_node.SD_exit()
			self.exp_node.unlock_node()
		if action.action=="sd_start_search":
			if verbose:
				print "%s: sd_start_search" % s
			self.exp_node.lock_node()
			self.exp_node.SD_start_search() #change
			self.exp_node.unlock_node()
		if action.action=="sd_stop_search":
			if verbose:
				print "%s: sd_stop_search" % s
			self.exp_node.lock_node()
			self.exp_node.SD_stop_search() #change
			self.exp_node.unlock_node()
		if action.action=="sd_publish":
			if verbose:
				print "%s: sd_publish" % s
			self.exp_node.lock_node()
			self.exp_node.SD_publish()  #change
			self.exp_node.unlock_node()
		if action.action=="sd_unpublish":
			if verbose:
				print "%s: sd_unpublish" % s
			self.exp_node.lock_node()
			self.exp_node.SD_unpublish() #change
			self.exp_node.unlock_node()
		if action.action=="wait_for_event":
			if verbose:
				print "%s: wait_for_event" % s
			wait_wrapper(self.name, action.parameter_list, self.exp_wait_marker_time)
			self.exp_wait_marker_time = 0
			
		if action.action=="wait_marker":
			if verbose:
				print "%s: wait_marker"  % s
			self.exp_wait_marker_time = datetime.datetime.now()
		
		if action.action=="wait_time":
			if verbose:
				print "%s: wait_time" %s
			if len(action.parameter_list)>0:
				if action.parameter_list["value"].type=="ref":
					print "ALERT! NOT IMPLEMENTED YET!"
				else:
					if simulate==True:
						return
					time.sleep(float(action.parameter_list["value"].data))
		
		if action.action=="fault_drop_sd_start":
			if verbose:
				print "%s: fault_drop_sd_start" %s
			self.exp_node.lock_node()
			self.exp_node.fail_start_drop_sd()
			self.exp_node.unlock_node()
			
		if action.action=="fault_drop_sd_stop":
			if verbose:
				print "%s: fault_drop_sd_stop" %s
			self.exp_node.lock_node()
			self.exp_node.fail_stop_drop_sd()
			self.exp_node.unlock_node()
			
		if action.action=="event_flag":
			if verbose:
				print "%s: event_flag"
				
			flag =action.parameter_list["value"].data  
			eh.inject_event("local","","%s"%flag,"")

		if action.action=="get_olsr":
			if verbose:
				print "%s: get_olsr" %s
			self.exp_node.lock_node()
			self.exp_node.get_olsr()
			self.exp_node.unlock_node()
									
		
	def run(self):
		'''
		This starts the execution of the actions
		'''
		global kill_threads
		
		for action in self.exp_action_list:
			if kill_threads!=1:
				self.exp_execute_action(action) #change
 				print "" ;
			else:
				print "Kill_threads flag is active!",kill_threads

def do_traffic_thread(queue, command, node, target, bw):
	r = 0
	try:
		node.lock_node()
		if command=="start":
			r = node.traffic_start(target,bw)
		if command=="update":
			r = node.traffic_update(target,bw)
		if command=="stop":
			#r = node.traffic_stop_all()
			r = node.traffic_stop(target)
			
	except socket.error:
		print "Socket error while trying to exec %s on node %s" %(command, str(node))
		if node.type=="env":
			print "Just an evn node, trying to continue..."
			error_log("Socket error while trying to exec %s on node %s"%(command,str(node)))
			r = -3
		else:
			print "Its an acting node, giving up experiment"
			error_log("Critical:Socket error while trying to exec %s on node ",node %(command))
			r = -2
	except IOError:
		print "Socket IO error, issue retry"
		r = -1
	finally:
		#print "Function:%s" % function
		node.unlock_node()	
		queue.put(r)

class exp_env_thread(threading.Thread):
	'''
	This thread represents the changes on the environment
	'''

	factor_value_run = None;

	def __init__(self, exp_desc,env_input_queue,env_output_queue,load_pairs= [], bw_changed=False):
		self.exp_desc = exp_desc
		self.exp_wait_marker_time = 0
		self.rand = random.Random()
		self.load_pairs = load_pairs
		self.env_input_queue = env_input_queue
		self.env_output_queue = env_output_queue
		self.bw_changed = bw_changed
		#self.current_bw = exp_desc.get_current_factor_value_by_id('fact_bw')
		threading.Thread.__init__(self, name="env")


	def parallel_traffic( self, command, RPCnodelist, target_list, bw):
		'''
		executes requests in parallel and waits for all to return
		returns a list of nodes, that gave a negative result
		'''			
		
		thread_list = []
		queue_list  = []
		failed_list = []
		
		if len(RPCnodelist)!=len(target_list):
			print "error, Both lists need same length"
			return RPCnodelist
		
		for i in range(len(RPCnodelist)):
			queue_list.append(Queue.Queue())
			th = threading.Thread( target=do_traffic_thread, kwargs={'queue':queue_list[i], 'node':RPCnodelist[i],'target':target_list[i],'command':command,'bw':bw} )
			thread_list.append(th)
			#time.sleep(0.15)
			th.daemon = True   
			th.start()
		
		for i in range(len(RPCnodelist)):
			ret=queue_list[i].get()
			if ret==-1:
				print "traffic returned -1"
				failed_list.append(RPCnodelist[i])
			if ret==-2:
				print "traffic returned -2"
				raise Exception
			if ret==-3:
				print "traffic gave up due to connect to env node"
	
		return failed_list

	def traffic(self, command, exp_action=0):
		global nodeContainer
		s = "ENV_Thread "
		#TODO choice
		if len(nodeContainer.all_env())<2:
			return
		
		random_seed = None
		
		if (command=="stop"):
			tmp_nodes = []

			for pair in self.load_pairs:
				tmp_nodes.append(pair[0])
				tmp_nodes.append(pair[1])

			parallel_exec(tmp_nodes, "traffic_stop_all")
		
		else:
			bw = 0
			random_pairs = 0
			random_switch_amount = 0
			removed_pairs = []
			added_pairs = []
			for (name, exp_param) in exp_action.parameter_list.items():
				if name=="random_pairs":
					if exp_param.type=="fix":
						random_pairs=exp_param.data
					else:
						random_pairs = exp.get_current_factor_value_by_id(exp_param.data)
				if name=="random_seed":
					if exp_param.type=="fix":
						random_seed=exp_param.data
					else:
						random_seed = exp.get_current_factor_value_by_id(exp_param.data)
				if name=="random_switch_seed":
					if exp_param.type=="fix":
						random_switch_seed=exp_param.data
					else:
						random_switch_seed = exp.get_current_factor_value_by_id(exp_param.data)
				if name=="random_switch_amount":
					if exp_param.type=="fix":
						random_switch_amount=int(exp_param.data)
					else:
						random_switch_amount = exp.get_current_factor_value_by_id(exp_param.data)
				if name=="bw":
					if exp_param.type=="fix":
						bw=exp_param.data
					else:
						bw = exp.get_current_factor_value_by_id(exp_param.data)

			# get pseudo randomly assigned pairs
			print "%s: getting %d pairs, bw=%d" % (s,random_pairs,bw)
			if random_pairs==0:
				return
			if (command=="start"):
				if random_seed==None:
					self.load_pairs = nodeContainer.get_random_env_pairs(random_pairs)
				else:
					self.load_pairs = nodeContainer.get_random_env_pairs(random_pairs, random_seed)
					
			if random_switch_amount>0:
				if random_switch_seed!=None:
					self.rand.seed(random_switch_seed)
				
				for i in range(random_switch_amount):
					# Choose random pair from current loadnodes
					currpair = self.rand.randrange(0,len(self.load_pairs))
					# Remove chosen pair from current loadnodes
					removed_pairs.append(self.load_pairs[currpair])
					del self.load_pairs[currpair]

					# Now pick a new random pair
					env_nodes = nodeContainer.all_env()

					currlist = list(range(len(env_nodes)))
					newpartner1 = currlist[self.rand.randrange(0, len(currlist))]
					currlist.remove(newpartner1)
					newpartner2 = currlist[self.rand.randrange(0, len(currlist))]
					newpair = [env_nodes[newpartner1],env_nodes[newpartner2]]
			
					self.load_pairs.append(newpair)
					added_pairs.append(newpair)
					print "%s: Replaced iperf pair %s with %s." % (s,removed_pairs[-1], newpair)

			# for each pair, start the clients
			tmp_nodes = []
			tmp_targets = []
			for pair in self.load_pairs:
				tmp_nodes.append(pair[0])
				tmp_targets.append(pair[1].name)
				
				tmp_nodes.append(pair[1])
				tmp_targets.append(pair[0].name)

			if command == "start":
				self.parallel_traffic("start",tmp_nodes,tmp_targets,bw)
				
			else:
				#if bw  == self.current_bw:
				if self.bw_changed:
					print "%s: Change in BW, stopping all traffic and restarting with new value." %s
					
					#self.current_bw = bw
					parallel_exec(tmp_nodes, "traffic_stop_all")
					self.parallel_traffic("start",tmp_nodes,tmp_targets,bw)
					#self.parallel_traffic("update",tmp_nodes,tmp_targets,bw)
				else:
					'''
					Since the load is the same only modify new pairs
					'''
					print "%s: Updating only new load pairs." %s
					# stop previous pairs, and start the new ones o
					stop_nodes = []
					stop_targets = []
					start_nodes = []
					start_targets = []
					for pair in removed_pairs:
						stop_nodes.append(pair[0])
						stop_targets.append(pair[1].name)
                        
						stop_nodes.append(pair[1])
						stop_targets.append(pair[0].name)
					for pair in added_pairs:
						start_nodes.append(pair[0])
						start_targets.append(pair[1].name)
                        
						start_nodes.append(pair[1])
						start_targets.append(pair[0].name)
					self.parallel_traffic("stop",stop_nodes,stop_targets,bw)
					self.parallel_traffic("start",start_nodes,start_targets,bw)
					
			self.env_output_queue.put(self.load_pairs)				
			
	def drop_sd_start(self):
		global nodeContainer
		all = nodeContainer.all()
		parallel_exec(all,"fail_start_drop_sd")
		
	def drop_sd_stop(self):
		global nodeContainer
		all = nodeContainer.all()
		parallel_exec(all,"fail_stop_drop_sd")
		
	def get_olsr(self):
		global nodeContainer
		all = nodeContainer.all()
		parallel_exec(all,"get_olsr")
		
	def exp_execute_action(self, exp_action):
		global verbose
		global simulate
		
		s = "ENV_Thread "
			
		if exp_action.action=="wait_for_event":
			if verbose:
				print "%s: wait_for_event" % s
			wait_wrapper( self.name, exp_action.parameter_list, self.exp_wait_marker_time)
			self.exp_wait_marker_time = 0
			
		if exp_action.action=="wait_marker":
			if verbose:
				print "%s: wait_marker"  % s
			self.exp_wait_marker_time = datetime.datetime.now()
			
		if exp_action.action=="env_traffic_start":
			print "%s: traffic_start" %s
			self.traffic("start", exp_action)
			
		if exp_action.action=="env_traffic_update":
			print "%s: traffic_update" %s
			self.traffic("update", exp_action)	
			
		if exp_action.action=="env_traffic_stop":
			self.traffic("stop")
		
		if exp_action.action=="wait_time":
			if verbose:
				print "%s: wait_time" %s
			if len(exp_action.parameter_list)>0:
				if exp_action.parameter_list["value"].type=="ref":
					print "ALERT! NOT IMPLEMENTED YET!"
				else:
					if simulate==True:
						return
					time.sleep(float(exp_action.parameter_list["value"].data))
		
		if exp_action.action=="env_start_drop_sd":
			if verbose:
				print "%s: env_start_drop_sd" %s
			self.drop_sd_start()
			
		if exp_action.action=="env_stop_drop_sd":
			if verbose:
				print "%s: env_stop_drop_sd" %s
			self.drop_sd_stop()
		
		if exp_action.action=="event_flag":
			if verbose:
				print "%s: event_flag" %s			 
			flag =exp_action.parameter_list["value"].data  
			eh.inject_event("local","","%s"%flag,"")
				 
		if exp_action.action=="get_olsr":
			if verbose:
				print "%s: get_olsr" %s
			self.get_olsr()
			
	def run(self):
		'''
		'''
		global kill_threads
		
		command = self.env_input_queue.get(True)
		print "ENV_Thread: Doing command %s" %(command)
		if command == "global":
			for action in self.exp_desc.global_process.action_list:
				if kill_threads!=1:
					self.exp_execute_action(action)
			
		elif command == "run":
			for action in self.exp_desc.env_process.action_list:
				if kill_threads!=1:
					self.exp_execute_action(action)
			
		else:
			print "Error: Invalid command recieved."
			exit()


def _create_actor_threads(exp, map):
	global nodeContainer
	print "Need to create %d threads " % map.get_num_of_total_instances()
	actor_list = []
	for i in range(map.get_num_of_actors()):
		aid = map.get_actor_id(i)
		for j in range(map.get_num_of_instances(aid)):
			iid = map.get_instance_id(aid, j)
			abstract_node = map.get_abstract_node(aid,iid)
			print "Creating thread instance %s for actor id %s on abstract node %s" %(iid,aid,abstract_node)
			node = nodeContainer.abstract_node_to_real_node(abstract_node)
			#exp.node_processes.summary()
			actor = exp.node_processes.get_actor(aid)
			newactor = exp_actor_thread("sd", exp, aid, iid, actor.sd_action_list, node)
			actor_list.append(newactor)
			if actor.has_fault_actions()==True:
				newactor = exp_actor_thread("fault", exp, aid, iid, actor.fault_action_list, node)
				actor_list.append(newactor)
	return actor_list




def build_full_run_matrix(full_run_matrix,run_matrix_done):
	
	#print full_run_matrix;
	found_flag =False;
	new_run_matrix = []
	NOP = ['N','N','N','N']
		#[A]Substract the two matrices and obtain a new_run_matrix 
			#The new_run_matrix contains ['N','N','N','N'] (NOP) in the places of the runs already done before while normal values (values of the full_matrix which is not done yet)
			#in the places that needs to be done this is done to preserve the same indexing system of the run_number that will be 
			#used later.
	
	#print step for debugging		
	#~ if verbose:
		#~ print "#########Full Matrix##################"
		#~ for run_item_full_run_matrix in full_run_matrix:
			#~ print run_item_full_run_matrix;


	for run_item_full_run_matrix in full_run_matrix:
		for run_item_run_matrix_done in run_matrix_done:
			if (run_item_full_run_matrix == run_item_run_matrix_done):
				#Found :Already done before
				found_flag =True; 
				new_run_matrix.append(NOP);
				break;
		#Finished searching 
		if (found_flag == False):		
			new_run_matrix.append(run_item_full_run_matrix);
		else: # True -> do nothing
			found_flag = False;

	#print step for debugging		
	#~ if verbose:
		#~ print "#########To be done##################"
		#~ for run_item_new_run_matrix in new_run_matrix:
			#~ print run_item_new_run_matrix;
	
	
	return new_run_matrix;
	
	
	
def sort_xml_file(xml_run_file):
	
	tree = ET.parse(xml_run_file);
	root = tree.getroot();
	
	#Fetch all the nodes and the
	runs_nodes =[] ;
	runs_nodes = root.findall('run_done');
	
	#sort them
	runs_nodes.sort(key=lambda run_node: int(run_node.get('run_matrix_value')));
	
	
	#remove what was in the xml file
	f = open(xml_run_file, 'r+')
	f.truncate();
	f.close();
	
	
	#Write to the xml file
	run_file_f = open(xml_run_file,"w+"); #Open the file for write and overwrite 
	
	s= '<run_list>\n';
	run_file_f.write(s);
	s= '</run_list>\n';
	run_file_f.write(s);
	run_file_f.close();
	
	
	tree = ET.parse(xml_run_file);
	root = tree.getroot();
	 
	for rundone in runs_nodes:
	  run_done=ET.Element("run_done",run_matrix_value = str(rundone.get('run_matrix_value')),value=str(rundone.get('value')));
	  root.append(run_done);
	  
	  for factor in rundone.findall('factor'):
	    run_factor=ET.Element("factor",id=str(factor.get('id')),index = str(factor.get('index')),size=str(factor.get('size')),value=str(factor.get('value')));
	    run_done.append(run_factor);
		
	tree.write(xml_run_file);
	indent(root);
	tree.write(xml_run_file);

def delete_last_runs(xml_run_file):
	
	##################################################################
	#Delete routine :delete the last three runs 
	##################################################################
	
	print "Deleting previous runs"
		#[1]remove the last three runs from the xml.
	tree = ET.parse(xml_run_file);
	root = tree.getroot();
	max_run  =0;
	curr_run =0;
	
	#instantiation to use only the methods
	exp_run = experiment_description(options.experiment_description);
			#[A] find the max. run
	for run_done in root.findall('run_done'):
		curr_run = int(run_done.get('value'))
		if curr_run > max_run:
			max_run =curr_run ;

	##print step for debugging
	if verbose:
		print "Max. run found";
		print max_run
	
	if(max_run == 0):
		print "No items to delete"
			#[B] find & delete runs above max_run - 3 from the xml file 
					#[I]case the total number of runs less that 4
	elif(max_run < 4):
		for run_done in root.findall('run_done'):
			run_time_value = int(run_done.get('value'))
			run_matrix_value = int(run_done.get('run_matrix_value'));
			#delete from the xml file
			root.remove(run_done);
			
			#delete from the Masterdir
			Master_dir_to_be_deleted  = "%s/%s" % (experiment_data.get_current_experiment_dir(),exp_run.factor_level_matrix.make_run_identifier(exp_run.run_matrix[run_matrix_value]));
			#delete from the node dir
			Node_dir_to_be_deleted = "%s/%s/%s/%s" % (experiment_root_nodes, results_dir_name_nodes,exp_run.experiment_name,exp_run.factor_level_matrix.make_run_identifier(exp_run.run_matrix[run_matrix_value])) ;
			try:
				shutil.rmtree(Master_dir_to_be_deleted)
			except:
				print "Error: while deleting %s" %(Master_dir_to_be_deleted)
			try:
				shutil.rmtree(Node_dir_to_be_deleted)
			except:
				print "Error: while deleting %s" %(Node_dir_to_be_deleted)
			
	
	else:

		for run_done in root.findall('run_done'):

			curr_run = int(run_done.get('value'))
			run_matrix_value = int(run_done.get('run_matrix_value'));

			if(curr_run > max_run - 20):
				
				#delete this run the xml file
				root.remove(run_done);
					
				Master_dir_to_be_deleted  = "%s/%s" % (experiment_data.get_current_experiment_dir(),exp_run.factor_level_matrix.make_run_identifier(exp_run.run_matrix[run_matrix_value]))
				Node_dir_to_be_deleted = "%s/%s/%s/%s" % (experiment_root_nodes, results_dir_name_nodes,exp_run.experiment_name,exp_run.factor_level_matrix.make_run_identifier(exp_run.run_matrix[run_matrix_value])) ;
					
				#delete Master and Nodes dir
				try:
					shutil.rmtree(Master_dir_to_be_deleted)
				except:
					print "Error: while deleting %s" %(Master_dir_to_be_deleted)
				try:
					shutil.rmtree(Node_dir_to_be_deleted)
				except:
					print "Error: while deleting %s" %(Node_dir_to_be_deleted)
				

	tree.write(xml_run_file);


	
	
def adjust_value_attribute(xml_run_file):
	
	tree = ET.parse(xml_run_file);
	root = tree.getroot();

	#Open the xml file and adjust the value attribute 
	new_actual_run_number =0;

	for run_done in root.findall('run_done'):
		run_done.set('value',str(new_actual_run_number));
		new_actual_run_number = new_actual_run_number+1;
	tree.write(xml_run_file);	

def build_run_matrix_done(run_file,run_matrix_done):
	
	old_run_item    = []
	
	tree = ET.parse(run_file)
	root = tree.getroot()
	runs_done = root.findall('run_done')
	
	for run_done in runs_done : 	
		for factor in run_done.findall('factor'):
			factor_id    =factor.get('id')
			factor_index =factor.get('index')
			factor_value =int(factor.get('value'))
			old_run_item.append(factor_value)
			
		run_matrix_done.append(old_run_item)

		old_run_item =[]
				

	#~ if verbose:
		#~ print "###########Done runs######################"
		#~ for run_item_run_matrix_done in run_matrix_done:
			#~ print run_item_run_matrix_done
	
	return run_matrix_done

def run_experiment(exp,new_run_matrix,xml_run_file):
	global nodeContainer
	global eh
	global kill_threads
	global forward

	

	NOP_RUN =['N','N','N','N'];

	actual_run_number =0;
	done_runs		  =0;
	factor_value_run =[];
	runs_positions_new_run_matrix =[];

	tree = ET.parse(xml_run_file);
	root = tree.getroot();


	#Process the xml file to adjust it with respect to time (actual_run_number)
		#compute how many runs already done and to add the value of the run based on the latest run.
	for run_number in range(0, len(new_run_matrix)):
		if (new_run_matrix[run_number] == NOP_RUN):
			done_runs = done_runs+1;
			runs_positions_new_run_matrix.append(run_number);


	#compute how many runs already done and to add the value of the run based on the latest run.
	for run_number in range(0, len(new_run_matrix)):
		if (new_run_matrix[run_number] == NOP_RUN):
			actual_run_number = actual_run_number+1;
	
	#print runs_positions_new_run_matrix;
		
	#if verbose:
	#	for i in range(0,len(runs_positions_new_run_matrix)):
	#		print runs_positions_new_run_matrix [i];

	#Adjust the value of the run_matrix_value
	i =0;
	for run_done in root.findall('run_done'):
		run_done.set('run_matrix_value',str(runs_positions_new_run_matrix[i]))
		i = i+1;
	tree.write(xml_run_file);	
	
	
		#loop over run sequence, resuming automatically with forward variable
	for run_number in range(0, len(new_run_matrix)):
		
		if (new_run_matrix[run_number] == NOP_RUN):
			#if verbose:
			#	print "Run number %d already_done" %run_number;
			
			run_done.set('run_matrix_value',str(run_number));
			#if verbose:
			#	print run_done.get('run_matrix_value');
	
	
	tree.write(xml_run_file);
		
	#Start environmental thread
	exp.set_run_number(0) #We need some information from the experiments that is run dependant in the env thread, get it for run zero to start with.
	current_bw = exp.get_current_factor_value_by_id('fact_bw')
	#env_nodes   = nodeContainer.all_env()
	#parallel_run_init(env_nodes, exp.get_current_run_name(), "env")
    
	load_pairs = []
	env_input_queue = Queue.Queue()
	env_output_queue = Queue.Queue()
	env_thread = exp_env_thread(exp,env_input_queue,env_output_queue,load_pairs)
    
	env_input_queue.put("global")
	env_thread.start()
	env_thread.join()
	load_pairs = env_output_queue.get(True)
	print "------------------"
	print load_pairs
	
			
	#loop over run sequence, resuming automatically with forward variable
	print "\n======= Starting experiment runs ======\n"
	sys.stdout.flush()
	for run_number in range(0, len(new_run_matrix)):
		sys.stdout.flush()
		if (new_run_matrix[run_number] == NOP_RUN):
			if verbose:
				print "Run number %d already_done" %run_number;
			
		else:
			###################################################################
			#update the xml file which contains information about each run done
			###################################################################
	
			#[1]From run number get factor combination
				#Create a new experiment_description just to use methods
			exp_run = experiment_description(options.experiment_description);
				#Set run number
			exp_run.set_run_number(run_number);									
				#get the factor combination :
			for factor in exp_run.factor_list:
				factor_value_run.append(exp_run.get_current_factor_level_by_id(factor.id));
				#if verbose:
				#	print factor_value_run ;
			#[2]Write this combination to the xml file
				#Build the xml file
			#build_xml_file(exp_run);
				#Add elements to factors to it where elements represent runs which has been done
				#Add a new element to the root represents the new run 
					#Actually run number gives an indication about the order of time at which the run have been done.
			run_done=ET.Element("run_done",value=str(actual_run_number),run_matrix_value=str(run_number));
			root.append(run_done);
				#Add the factor characterization for each run.
			i =0;
			for factor in exp_run.factor_list:
				i =i+1;
				run_factor=ET.Element("factor",id=str(factor.id),size=str(factor.levels.get_len()),index=str(i),value=str(exp_run.get_current_factor_level_by_id(factor.id)));
				run_done.append(run_factor);
			
	
			indent(root);	
			tree.write('run_file.xml');
	
			actual_run_number = actual_run_number+1;
	
			###################################################################
			#Done update the xml
			###################################################################



			###### SETUP LEVELS OF ALL FACTORS FOR THIS RUN ########
			exp.set_run_number(run_number)
			nodeContainer.update_actor_nodes()
			run_definition = exp.get_run_identifier()
			print "run number %d starting with factor combination %s" %(run_number,run_definition)
			
			
			# clear log so the list won't get too long and the list object is blocked so long,
			# that remote clients time-out 
			eh.clear_log()
			kill_threads = 0
			try:
				###### PREPARE NETWORK FOR RUN ################################
				parallel_exec(nodeContainer.all(),"fail_start_drop_sd" )
				try:
					#measure clock offsets
					measure_time_diff_via_communication_channel()
					time.sleep(1)
				except:
					pass
				finally:
					parallel_exec(nodeContainer.all(), "fail_stop_drop_sd" )
				#################################################################

				actor_nodes = nodeContainer.all_actors()
				env_nodes   = nodeContainer.all_env()

				# init all
				try:
					parallel_run_init(actor_nodes,exp.get_current_run_name(), "actor")
				except:
					error_log("could not init run on at least one of the acting nodes, aborting")
					
				parallel_run_init(env_nodes, exp.get_current_run_name(), "env")
	
				map = exp.get_actor_node_map()
				
				new_bw = exp.get_current_factor_value_by_id('fact_bw')
				changed_bw = not (new_bw == current_bw)
				print "Changed data rate: " + str(changed_bw)
				if (changed_bw):
					current_bw = new_bw
				
				print "Creating Actor Threads"
				actor_list = _create_actor_threads(exp, map)			
				env_thread = exp_env_thread(exp,env_input_queue,env_output_queue,load_pairs,changed_bw) 
				actor_list.append(env_thread)
				
				print "Sending update message to Env Thread"
				#if env_thread.is_alive()==False:
				#	print "Env Thread is dead"
				env_input_queue.put("run")
	
				print "Running %d threads" %len(actor_list)
				# start threads
				for t in actor_list:
					t.start()			
				
				wait_for_threads_or_timeout(actor_list,exp.max_run_time)
				for t in actor_list:
					t.join()   
					
				load_pairs = env_output_queue.get(True)
				print "------------------"
				print load_pairs
				
				print "all threads finished"
				parallel_exec(actor_nodes, "run_exit")
				parallel_exec(env_nodes, "run_exit")
			except:
				raise

			actor_list =[]


	print "Leaving run function"
	 
def parallel_experiment_init(name, experiment_root, nodes, cap_interface, exp_protocol):
	print "starting experiment %s" % name
	
	failed=parallel_exec(nodes, "experiment_init", experiment_root, name, cap_interface, exp_protocol)
	if len(failed)!=0:
		print "First try had fails", failed
		parallel_exec(failed, "experiment_exit", experiment_root, name, cap_interface, exp_protocol)
		failed = parallel_exec(failed, "experiment_init", experiment_root, name, cap_interface, exp_protocol)
		if len(failed)!=0:
			print "Error, cannot init experiment on nodes ", failed
			return -1
	return 0

def parallel_run_init(nodes, name, role):
	'''
	Initialises the nodes, blocks until all are done or 
	returns an error when not
	Before it retries automatically once
	'''
	try:
		failed=parallel_exec(nodes,"run_init",name, role)
		if len(failed)!=0:
			parallel_exec(failed, "run_exit")
			failed = parallel_exec(failed, "run_init",name,role)
			if len(failed)!=0:
				print "Error, cannot init run on nodes ", failed
				return -1
		return 0
	except Exception, e:
		raise
	
	
		
class exp_experiment_data:
	'''
	This class contains all the data for an experiment (not just the run)
	and provides management functions relating a whole experiment
	'''
	def __init__(self, experiment_name, exp, xmldescription):
		self.experiment_dir = "MasterResults/%s" % (experiment_name)
		if not os.path.exists(self.experiment_dir):
			os.makedirs(self.experiment_dir)
		self.exp = exp
		self.xmldescription_file = xmldescription
	
	def set_current_experiment_dir(self, dir):
		self.experiment_dir=dir
		
	def get_current_experiment_dir(self):
		return self.experiment_dir

	def copy_files(self):
		print "Copying the used script files into the MasterResults directory"
		try:
			shutil.copy2(os.path.realpath(__file__),"%s/ExperiMaster.py" %self.experiment_dir)
			shutil.copy2("%s/exp_description.py" % os.path.expanduser("~"), "%s/exp_description.py" % self.experiment_dir)
			shutil.copy2("%s/Master_EventHandler.py" % os.path.expanduser("~"), "%s/Master_EventHandler.py" % self.experiment_dir)
			shutil.copy2("%s"% self.xmldescription_file , "%s/" % (self.experiment_dir))
		except Exception, e:
			print "There was a problem copying the experiment files to the Results folder", e
		
		

class RPCNode(xmlrpclib.ServerProxy):
	'''
	This class extends the xmlrpclib.ServerProxy class 
	with a couple of properties and methods that are used
	for the experimentation system.
	'''
	#ip   = ""
	#name = ""
	#node = None
	#state = 0
	def __init__(self, node_name, node_ip, abstract_id):
		self.name = node_name
		self.ip   = node_ip
		self.abstract_id = abstract_id
		if abstract_id=="":
			self.type = "env"
		else:
			self.type = "actor"
		self.action_lock = threading.Lock()
		xmlrpclib.ServerProxy.__init__(self,"http://%s:8000" % node_name)
		

	def lock_node(self):
		self.action_lock.acquire()
		#print "lock %s acquired" %self.name
	
	def unlock_node(self):
		self.action_lock.release()
		#print "lock %s released" %self.name
		pass
	
	
class SimuNode():
	'''
	This is a fake node, that does nothing, it's a simulation
	replacement for RPCNode
	'''
	def __init__(self, name, node_ip, abstract_id):
		self.name = name
		self.ip = node_ip
		
		self.abstract_id = abstract_id
		if abstract_id=="":
			self.type = "env"
		else:
			self.type = "actor"
		self.action_lock = threading.Lock()
		pass
	def lock_node(self):
		self.action_lock.acquire()
	def unlock_node(self):
		self.action_lock.release()
		
	def experiment_init (self, root_dir, experiment_name, capture_interface, sdp_type):
		pass
	def experiment_exit(self):
		pass
	def run_init(self, name, role):
		pass
	def run_exit(self):
		pass
	def get_topology(self, partners):
		pass
	def SD_init(self):
		pass
	def SD_exit(self):
		pass
	def SD_publish(self):
		pass
	def SD_unpublish(self):
		pass
	def SD_start_search(self):
		pass
	def SD_stop_search(self):
		pass
	def capture_start(self):
		pass
	def capture_stop(self):
		pass
	def traffic_start(self, servernode, bandwidth):
		pass
	def traffic_stop_all(self):
		pass
	def fail_start_drop_sd(self):
		pass
	def fail_stop_drop_sd(self):
		pass
	 
class NodeContainer:
	"""
	This Container shall contain all the nodes that 
	belong to an experiment. They can have a mapping
	to abstract nodes, when they take a role in service
	discovery, or they are just environment nodes that
	can be used to create traffic or other possible 
	influences on the service discovery process.
	
	For each node, the hostname and the ip should be specified.
	"""
	def __init__(self, specs_node_list):
		global simulate
		self.rand = random.Random()
		for node in list(specs_node_list):
			found = 0
			for check in specs_node_list:
				if node==check:
					found=found + 1
			if found>1:
				print "Double entry %s in node file" %node
				exit()
			 
			
		self.node_list = []
		for node_name in specs_node_list:
			if simulate==False:
				self.node_list.append(RPCNode(str(node_name['real_id']), str(node_name['real_ip']), str(node_name['abstract_id']) ))
			else:
				self.node_list.append(SimuNode(node_name['real_id'], node_name['real_ip'], node_name['abstract_id'] ))
		
	def PrintStatus(self):
		print "NC: %d nodes in file." % (len(self.node_list))

	def get_random_env_pairs(self, numberofpairs, random_seed=0):
		'''
		Here we use truly random pairs, this means that is possible to have multiple
		instances of the same pair, or nodes participating in multiple pairs.
		'''
		if random_seed!=0:
			self.rand.seed(random_seed)
		if len(self.node_list) >= 2:
			partners=[]
			for partner in range(numberofpairs):
				env_nodes = nodeContainer.all_env()
				#env_nodes = nodeContainer.all_env()
				currlist = list(range(len(env_nodes)))
				partner1 = currlist[self.rand.randrange(0, len(currlist))]
				currlist.remove(partner1)
				partner2 = currlist[self.rand.randrange(0, len(currlist))]
				partners.append( [env_nodes[partner1],env_nodes[partner2]]) 
			return partners
		else:
			print "NC: Not enough nodes to pick from."
			return None
	
	def all(self):
		'''
		returns the RPC node objects
		'''
		return self.node_list

	def all_env(self):
		'''
		returns all the RPC objects, that are env
		'''
		result = []
		for n in self.node_list:
			if n.type=="env":
				result.append(n)
		return result
	
	def all_actors(self):
		'''
		returns all the RPC objects, that are currently (this run) acting
		'''
		result = []
		for n in self.node_list:
			if n.type=="actor":
				result.append(n)
		return result
	
	def all_can_be_actors(self):
		'''
		returns all the nodes, that can be actor in the experiment
		(all that have a mapping to an abstract node)
		'''
		result = []
		for n in self.node_list:
			if n.abstract_id!="":
				result.append(n)
		return result
		
	def abstract_node_to_real_node(self, abstract_node):
		'''
		this mapping should come from a config file
		'''
		for node in self.node_list:
			if node.abstract_id == abstract_node:
				return node

	def update_actor_nodes(self):
		'''
		This function updates the node types according to the current (run)
		to allow to other functions to return the correct values.
		'''
		map=exp.get_actor_node_map()
		#set all nodes taking abstract roles to type 
		#depending on whether they are in the current mapping
		for node in self.node_list:
			abstract=node.abstract_id
			if abstract!="":
				if map.contains_abstract_node(abstract):
					node.type = "actor"
				else:
					node.type = "env"		
			
		
	def summary(self):
		print "NodeContainer"
		for node in self.node_list:
			print "\t node %s is abstract node %s, (IP:%s) and type %s" %(node.name,node.abstract_id,node.ip,node.type)
	
def measure_time_diff_via_communication_channel():
	'''
	This is the function that creates a listing of 
	of the clocking offsets between the master clock
	and the nodes
	'''
	global nodeContainer
	global experiment_data
	global exp
	
	os.makedirs("%s/%s" %(experiment_data.get_current_experiment_dir(),exp.get_current_run_name() ))
	nodes = nodeContainer.all_actors()
	if verbose:
		print nodes
	for node in nodes:
		cmd = "ping -T tsonly -c 1 %s" % (node.name)
		ret = 0
		output = open("%s/%s/ping_t_%s" %(experiment_data.get_current_experiment_dir(),exp.get_current_run_name(),node.name),"w")
		args = shlex.split(cmd)
		if verbose:
			print "executing ", cmd
		p = subprocess.Popen(args, stdout=output)
		p.communicate()
		output.close()
				


############################################################
#build_xml_file function
############################################################

def build_xml_file(exp_desc,xml_run_file):

	##############XML Layout##############################
	#Write data to the xml file (run_exp_encode)
	#run_exp_encode :This file contains the runs that have been done with the factors combinations
	#<!-- Number of factor = 4 -->
	#<runs_list>
	#	<!-- Run number 0 --> 
	#	<run value ="0">
	#   	<factor id="" index="" value=""\>               
	#       <factor id="" index="" value=""\>          
	#       <factor id="" index="" value=""\>          
	#       <factor id="" index="" value=""\>        					
	#        </run>
	#
	#	<!--Run number 1 -->
	#	.
	#   .
	#   .
	#
	#</run_list>
	#########################################################

	
	if(os.path.exists(xml_run_file) == False): #create a new file only if it doesn't exists
		print "creating a new run_file.xml"

		#Create a new experiment_description just to use its methods
		Exp_Enc_f = open("run_file.xml","w+"); #Open the file for write and overwrite 
		s='<!-- Number of factor = %d -->\n'%len(exp_desc.factor_list);
		Exp_Enc_f.write(s);
		s= '<run_list>\n';
		Exp_Enc_f.write(s);
		s= '</run_list>\n';
		Exp_Enc_f.write(s);
		Exp_Enc_f.close();

	else:
		#The file already exists
		print "The file run_file.xml already exists"	


if __name__ == '__main__':
	global eh
	global kill_threads
	global nodes_list
	global verbose
	global nodeContainer
	global error_log_lock
	global experiment_data
	global forward
	global simulate
	verbose = True #change
	eh_verbose = False
	simulate = False
	error_log_lock = threading.Lock()

	kill_threads = 0

	# specifics
	capture_interface      = "bmf0"
	experiment_root        = os.path.expanduser("~")
	experiment_root_nodes  = "%s/testbed" % experiment_root
	# Should be synchronized with Node_ManagerRPC.py on nodes
	results_dir_name_nodes = "results"
	forward  = 0
	forwardelement = "run_0_0_0_0"

	factor_level_matrix  = None 
	factor_weight_matrix = None 
	fact_value_run_matrix_Master= None 

	old_run_item 	= None
	new_run_item 	= None
	run_matrix_done = None
	full_run_matrix = None
	new_run_matrix  = None
	NOP 			= None


	factor_level_matrix  = []
	factor_weight_matrix = []
 	
	fact_value_run_matrix_Master  = []
	fact_value_run_matrix_Nodes   = []
	max_current_run_count_Master  = 0
	max_current_run_count_Nodes   = 0
	current_run_count_Master 	  = 0
	current_run_count_Nodes 	  = 0

	full_run_matrix =[]
	
	new_run_item    =[]
	run_matrix_done =[]
	new_run_matrix  =[]
	NOP 		    =['N','N','N','N']

	miss_match_flag = False




	# Option parser ############################################################
	parser = optparse.OptionParser(
		description='Run Service Discovery Experiments.',
		prog=os.path.basename(sys.argv[0]),
		version='%s 0.0.4' % os.path.basename(sys.argv[0]),
	)

	parser.add_option('-f'			, metavar='experiment description', dest='experiment_description',					help='file with description')
	parser.add_option('--rf' 		, metavar='xml run file', 			type = "string",	dest='xml_run_file',		default = 'run_file.xml',	help='file with description')
	parser.add_option('-v'			, metavar='verbose',				action='store_true', dest='verbose', 			default = True, 	help='Give this option to produce more output')
	parser.add_option('--ve'		, metavar='event handler verbose',	action='store_true', dest='eh_verbose', 		default = False,	help='Activate verbosity on the event handler (EH)')
	parser.add_option('--simulate'	, metavar='simulate',				action='store_true', dest='simulate',			default = False, 	help='Simulates a run without calling RPCs and without waiting')
	parser.add_option('--del'		, metavar='delete runs',			action='store_true', dest='delete_last_runs',	default = False,  	help='When restarting an experiment delete the last three runs');

	options, arguments = parser.parse_args()

	if options.experiment_description == None:
		print 'No xml experiment description file given.'
		exit()
		
	simulate   = options.simulate
	verbose    = options.verbose
	eh_verbose = options.eh_verbose


	#instantiation to use only the methods
	exp_run = experiment_description(options.experiment_description);
	experiment_name = "%s" % exp_run.experiment_name
	experiment_data = exp_experiment_data(experiment_name, exp_run, options.experiment_description)

	#Build the xml file which contains the runs that have been already done
	build_xml_file(exp_run,options.xml_run_file);

	# forward option has been disabled as resume is done automatically now
# 	if options.forward!=None:
# 		forward = int(options.forward)
# 		print "Forwarding the experiment to run %d" % forward
	############################################################
	nodeContainer = None
	
	
	#Adjust the value attribute
	adjust_value_attribute(options.xml_run_file)
	
	if options.delete_last_runs:
		delete_last_runs(options.xml_run_file)
	
	#Obtain the previous runs
	tree = ET.parse('run_file.xml');
	root = tree.getroot();


	sort_xml_file(options.xml_run_file);

	
	run_matrix_done = build_run_matrix_done(options.xml_run_file,run_matrix_done)
		

	#Obtain the full_run_matrix
	exp_with_new_config = experiment_description(options.experiment_description)
	full_run_matrix = exp_with_new_config.get_run_matrix()
	
	new_run_matrix = build_full_run_matrix(full_run_matrix,run_matrix_done)

	

	if (all(x==new_run_matrix[0] for x in new_run_matrix) == True):
		if(new_run_matrix[0] == NOP):
			print "The experiment is complete"
			exit()
	
		
	
	exp = experiment_description(options.experiment_description)
	if verbose:
		exp.summary()

	
	if exp.sd_protocol.lower() == "zeroconf".lower():
		exp_protocol = "avahi"
		print "Using protocol Zeroconf"
	elif exp.sd_protocol.lower() == "slp".lower():
		exp_protocol = "slp"
		print "Using protocol SLP"
	else:
		print "Unsupported protocol set. Change to slp or zeroconf"
		exit()




	experiment_data.copy_files()
	nodeContainer = NodeContainer(exp.get_all_spec_nodes())

	if verbose:
		nodeContainer.summary()

	eh = EventHandler(options.eh_verbose)
	eh.start_event_handler()

	try:
		if parallel_experiment_init(experiment_name, experiment_root, nodeContainer.all(), capture_interface, exp_protocol)==-1:
			print "Cannot init experiment on all nodes, aborting!"
			kill_threads = 1
			eh.stop_event_handler()
			exit()
		
		can_be_actors = nodeContainer.all_can_be_actors()
		can_be_names = []
		for can_be in can_be_actors:
			can_be_names.append(can_be.name)
		print "Getting Topology information on the nodes that can act",can_be_names
		parallel_exec( can_be_actors, "get_topology",can_be_names)
		run_experiment(exp,new_run_matrix,options.xml_run_file)
		
	except (KeyboardInterrupt, SystemExit):
		print "Have to quit now..."
		kill_threads = 1
	finally:
		kill_threads = 1
		parallel_exec(nodeContainer.all(), "fail_stop_drop_sd" )
		time.sleep(1)
		parallel_exec(nodeContainer.all(), "experiment_exit")
		time.sleep(10)
		eh.stop_event_handler()

	print "Experiment done with all runs"
	print "Waiting 5 seconds for all threads to abort"
	sendmail("Experiment Complete","Experiment %s has finished." % experiment_data.get_current_experiment_dir())
	time.sleep(5)
	exit()
