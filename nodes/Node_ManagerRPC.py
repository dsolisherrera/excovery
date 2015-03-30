'''
Created on 15.01.2012
@author: stefan

This script is meant to run as server on each node, listening to requests via RPC.
It allows for a stateful client representation.

'''


from SimpleXMLRPCServer import SimpleXMLRPCServer
from SimpleXMLRPCServer import SimpleXMLRPCRequestHandler
import xmlrpclib
import subprocess
import datetime
import time
import shlex
import os
import sys
import ctypes

sys.path.append('/home/solished/exp_root/usr/lib/SLPPython')
ctypes.cdll.LoadLibrary('/home/solished/exp_root/usr/lib/libslp.so.1')
import thread
import glob
import socket
import shutil
import Queue
import threading
import slp
import _slp
from collections import defaultdict

# Restrict to a particular path.
class RequestHandler(SimpleXMLRPCRequestHandler):
	rpc_paths = ('/RPC2',)        



def kill_and_wait(programname):
	'''
	Kills  a programname via killall
	'''
	cmd = "sudo killall -9 -q %s" % programname
	args = shlex.split(cmd)
	p = subprocess.Popen(args)
	p.wait()
	
class event_sender_thread(threading.Thread):
	'''
	This class works on a queue to send xml rpc requests to the master
	'''
	global kill_threads
	def __init__(self, queue):
		self.queue = queue
		# Master connection remains active after first init
		self.master = xmlrpclib.ServerProxy("http://%s:8000" % "uhu")
		threading.Thread.__init__(self, name="event sender thread")
		
	def run(self):
		while kill_threads!=1:

			(name,ts,type,param)=self.queue.get()
			try:
				
				self.master.event(name, ts, type, param)
			except Exception:
				print "Problem with event connection!", sys.exc_info()[0]
				print "trying again"
				try:
					self.master.event(name, ts, type, param)
				except Exception:
					print "Problem persists... this event is dropped"
			
		
		
class ExpNodeManager:
	'''
	This class represents all the actions that can be done on a node
	that participates in a sd experiment
	'''
	# Class Variables (visible in all instances)
	capture_running   = 0
	sd_daemon_running = 0
	sd_search_running = 0
	sd_publish_running= 0
	experiment_inited = 0
	run_inited        = 0
	state_dropping    = 0
	netlink_manager   = None
	sleep_counter     = 0
	iperf_client_processes = defaultdict(list)
	iperf_client_logfiles  = defaultdict(list)
	iperf_server_process = None
	_saveout   = sys.stdout   
	_saveerr   = sys.stderr
	_log_fsock = None
	event_thread = None
	event_queue  = None
	#file handles
	_file_event_log = None
	
	# service configs
	_service_type = ""
	_service_name = ""
	_sdp_type     = ""
	
	# SLP handle
	slph = ""
	
	#node config
	_node_name        = ""
	_node_ip        = ""
	_experiment_name  = ""
	_current_run_name = ""
	_current_run_role = "env" # capturing is only done when "actor", with "env" not 
	#paths
	_root_dir         = ""
	_experiment_dir   = ""
	_topology_dir     = "" 
	_run_dir          = ""
	_links_dir        = ""
	_env_dir          = ""
	_service_file_dir = "" # should come from static avahi specific config file
	_results_dir_name = "results"
	_capture_dir_name = "capture"

	_traffic_interface = "wlan2"
	
	def _dirs_configure_run_dir(self, root, results, experiment, run):
		'''
		sets the path of the current run
		Also creates the dir in case it doesn't exist yet.
		'''
		self._run_dir="%s/%s/%s/%s" %( root,results,experiment,run)
		if self._current_run_name=="":
			return 0
		
		if not os.path.exists(self._run_dir):
			try:
				os.makedirs(self._run_dir)
			except os.error:
				print "Dir %s exists or cannot be created" % self._run_dir
			os.chown(self._run_dir, self._uid, self._gid)

	def _dirs_configure_env_dir(self):
		'''
		sets the path of the current run's env 
		Also creates the dir in case it doesn't exist yet.
		'''
		self._env_dir = "%s/env" % self._run_dir
		if self._current_run_name=="":
			return 0
		if not os.path.exists(self._env_dir):
			try:
				os.makedirs(self._env_dir)
			except os.error:
				print "Dir %s exists or cannot be created" % self._env_dir
			os.chown(self._env_dir, self._uid, self._gid)

	def _dirs_configure_routes_dir(self):
		'''
		sets the path of the current run's env 
		Also creates the dir in case it doesn't exist yet.
		'''
		self._routes_dir = "%s/routes" % self._run_dir
		if self._current_run_name=="":
			return 0
		if not os.path.exists(self._routes_dir):
			try:
				os.makedirs(self._routes_dir)
			except os.error:
				print "Dir %s exists or cannot be created" % self._routes_dir
			os.chown(self._routes_dir, self._uid, self._gid)

	def _dirs_configure_links_dir(self):
		'''
		sets the path of the current run's env 
		Also creates the dir in case it doesn't exist yet.
		'''
		self._links_dir = "%s/links" % self._run_dir
		if self._current_run_name=="":
			return 0
		if not os.path.exists(self._links_dir):
			try:
				os.makedirs(self._links_dir)
			except os.error:
				print "Dir %s exists or cannot be created" % self._links_dir
			os.chown(self._links_dir, self._uid, self._gid)

	def _dirs_configure_experiment_dir(self, root, results, experiment):
		'''
		Sets the path of the current experiment
		Also creates the dir in case it doesn't exist yet.
		
		Also sets up topology directory
		'''
		self._experiment_dir="%s/%s/%s" %( root,results,experiment)
		self._topology_dir = "%s/topology" %self._experiment_dir
		if not os.path.exists(self._experiment_dir):
			try:
				os.makedirs(self._experiment_dir)
			except os.error:
				print "Dir %s exists or cannot be created" % self._experiment_dir
				
			os.chown("%s/%s"%(root,results), self._uid, self._gid)
			os.chown(self._experiment_dir, self._uid, self._gid)
			
		if not os.path.exists(self._topology_dir):
			try:
				os.makedirs(self._topology_dir)
			except os.error:
				print "Dir %s exists or cannot be created" % self._topology_dir
			os.chown(self._topology_dir, self._uid, self._gid)
	
	def _dirs_configure_capture_dir(self, root, results, experiment, run):
		'''
		Sets the path of the current run's capture files
		'''
		self._capture_dir="%s/%s/%s/%s/%s/" %( root,results,experiment,run, self._capture_dir_name)
		if self._current_run_name=="":
			return 0
		
		if not os.path.exists(self._capture_dir):
			try:
				os.makedirs(self._capture_dir)
			except os.error:
				print "Dir %s exists or cannot be created" % self._capture_dir
			os.chown(self._capture_dir, self._uid, self._gid)
		
	def experiment_init (self, root_dir, experiment_name, capture_interface, sdp_type):
		'''
		Inits the whole experiment. Creates experiment dir if not there already.
		Results will be placed in that subdirectory.
		* configures sdp_type to be used
		* configures root_dir
		* configures the interface for capturing network traffic
		
		@param sdp_type can be "avahi"
		init cannot reinit - exit is needed first
		'''
		print "experiment_init(%s,%s%s,%s)" %(root_dir,experiment_name,capture_interface,sdp_type)
		if self.experiment_inited == 1:
			return -1
		if capture_interface==None:
			return -1
		print "initalising experiment"
		self._node_name = socket.gethostname()
		self._node_ip = socket.gethostbyname(socket.gethostname())
		self._experiment_name = experiment_name
		self._root_dir = root_dir
		self._exp_root_dir = "%s/exp_root" % self._root_dir
		self._sdp_type = sdp_type

		self._saveout = sys.stdout
		self._saveerr = sys.stderr
		
		if self._configure_service(self._sdp_type)==-1:
			return -1
		
		self._dirs_configure_experiment_dir(self._root_dir, self._results_dir_name, self._experiment_name)
			
		#open the Node Manager's output file, append in case there is already one
		logfile='%s/RPC-Server_%s.log'%(self._experiment_dir,self._node_name)
		self._log_fsock = open(logfile, 'a')
		os.chown(logfile, self._uid, self._gid)                             
		sys.stdout = self._log_fsock                                       
		sys.stderr = self._log_fsock
		print "UID=%d %s" % (self._uid,os.getenv("SUDO_UID"))
		print "GID=%d" % self._gid
		print "UID is %d " % int(os.getenv("SUDO_UID"))
		print "GID is %d " % int(os.getenv("SUDO_GID"))
		
		try:
			shutil.copy2("Node_ManagerRPC.py","%s/"%self._experiment_dir)
		except Exception, e:
			print "Error while trying to copy script to experiment folder", e
		
		#Set inital location for traffic generation logs
		
		self._env_dir = "%s/env" %(self._experiment_dir)
		if not os.path.exists(self._env_dir):
			try:
				os.makedirs(self._env_dir)
			except os.error:
				print "Dir %s exists or cannot be created" % self._env_dir
			os.chown(self._env_dir, self._uid, self._gid)
		
		
		# Setup implementation specific variables
		print "Initializing experiment %s" % (experiment_name)
		
		self._cap_interface=capture_interface        

		self._capture_process = None
		self._daemon_process  = None
		self._publish_process = None
		self._browser_process = None
		# call base class init method
		self.experiment_inited = 1
		
		#start iperf server on all participating nodes
		if self.iperf_server_process!=None:
			self.iperf_server_process.kill()
			self.iperf_server_process.wait()
			self.iperf_server_process = None
			
		#cmd = "iperf -u -s -i 5 -D 1>>~/Logs/iperf/iperf_%s_s 2>&1 &" % (self._node_name)
		cmd = "iperf -u -s -i 5 "   
		args = shlex.split(cmd)
		#print "Executing %s" % cmd
		#self.iperf_server_logfile = "%s/iperf_server.log" %(self._env_dir)
		self.iperf_server_process=subprocess.Popen(args)
		print "Iperf client started"              
		
		time.sleep(1)
		self._generate_event("experiment_init","")
		self.experiment_inited=1
		return 0
	
	def experiment_exit(self):
		'''
		This can always be called, it finishes any pending processes
		and ends the experiment graciously
		'''
		print "experiment_exit"
		self._generate_event("experiment_exit","")
		#todo: check what else should be removed or cleaned up here
		self.SD_exit() # SD_stop stops all subprocesses
		self.capture_stop()
		self.traffic_stop_all()
		if self.iperf_server_process!=None:
			self.iperf_server_process.kill()
			self.iperf_server_process.wait()
			self.iperf_server_process = None
		self.experiment_inited = 0
		sys.stdout = self._saveout   
		sys.stderr = self._saveerr
		if self._log_fsock!=None:
			self._log_fsock.close()
			self._log_fsock=None
		return 0
		
	def run_init(self, name, role):
		'''
		Inits one run of an experiment.
		@name The name of the run, used to identify it. A directory is created in the Experiment's
		directory with that name in which all the run-specific data is stored.
		@param role: if this run is initialised as actor in the sd process. if not, this
		node is considered to be a environment node (no capture)
		init will return an error if it is already inited, it needs to be exited first.
		'''
		print "run_init(%s)" % name
		if self.experiment_inited==0:
			return -1
		if self.run_inited==1:
			return -1
		print "initialising run"
		self._current_run_name = name
		if role=="actor":
			self._current_run_role = "actor"
		else:
			self._current_run_role = "env"
			
		self._dirs_configure_run_dir(self._root_dir, self._results_dir_name, self._experiment_name, self._current_run_name)
		self._dirs_configure_capture_dir(self._root_dir, self._results_dir_name, self._experiment_name, self._current_run_name)
		self._file_event_log = open('%s/event_log_%s.log'%(self._run_dir,self._node_name), 'a')
		self._file_event_log.write("timestamp,type,param\n")
		self._dirs_configure_env_dir()
		self._dirs_configure_routes_dir()
		self._dirs_configure_links_dir()
		cmd = ["/bin/bash", "bin/routes_alive.sh", "%s/%s.log"% (self._routes_dir, self._node_name)]
		#print "Checking routes ", cmd
		p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
		self.capture_start()
		p.communicate()
		sys.stdout.flush()


		self._generate_event("run_init",self._current_run_role)
		sys.stdout.flush()
		self.run_inited = 1
		return 0
		
	def run_exit(self):
		'''
		exits one run, does all the steps necessary to stop
		everything that has been started in run_init
		exit can always be savely called and it will exit
		'''
		print "run_exit"
		self.SD_exit()
		self.capture_stop()
		
		self._current_run_name = ""        
		self._dirs_configure_run_dir(self._root_dir, self._results_dir_name, self._experiment_name, self._current_run_name)
		self._dirs_configure_capture_dir(self._root_dir, self._results_dir_name, self._experiment_name, self._current_run_name)
		self._dirs_configure_env_dir( )
		self._generate_event("run_exit","")
		if self._file_event_log!=None:
			self._file_event_log.close()
		self._file_event_log = None
		self.run_inited = 0
		sys.stdout.flush()
		return 0
		
	def __del__(self):
		None
		
	def get_topology(self, partners):
		'''
		retrieves a topology information
		'''
		print "get_topology"
		procs =[]
		outputs = []
		if self.experiment_inited == 0:
			return -1
		print partners
		for partner in partners:
			print partner
			if partner == self._node_name:
				continue
			cmd = "traceroute -w 10 -z 100 -q 10 %s-%s" % (partner,self._traffic_interface)
			ret = 0            
			output = open("%s/traceroute_%s_%s" %(self._topology_dir,self._node_name,partner),"w")
			outputs.append(output)
			args = shlex.split(cmd)
			print "executing ", cmd
			p = subprocess.Popen(args, stdout=output)
			procs.append(p)
		for p in procs:
			p.wait()
		for o in outputs:
			o.close()
		print
		return 0
	
#################################################################
# HELPER FUNCTIONS
################################################################

	def _cleanup_service(self, type):
		if type=="avahi":
			filelist=glob.glob("%s/*%s" % (self._service_file_dir, self._service_file_post))
			for file in filelist:
				if os.path.exists(file):
					os.remove(file)
		else:
			logfile = "%s/etc/slpd/services/slp-%s.log" % (self._exp_root_dir, self._node_name) 
			if os.path.exists(logfile):
					os.remove(logfile)

	def _configure_service(self, stype):
		if stype=="avahi":
			self._service_type="_test._udp"
			self._service_port="12345"
			self._service_file_dir="%s/etc/avahi/services" %(self._exp_root_dir)
			self._service_file_post=".service"
			self._service_name="svc-%s" % self._node_name
	 #   if type=="slpd":
		else:
			name = "_".join(self._current_run_name.split('_')[-2:])
			#self._service_slp_url = "service:test_%s://10.0.0.1/testing/%s" %(name,self._node_name)
			self._service_slp_url = "service:test2://10.0.0.1/testing/%s" %(self._node_name)
		#	self._service_slp_url = "service:_test._udp://%s" % self._node_ip
			self._service_slp_attrs = { 'nodeId': '%s' %(self._node_name)} 
			#self._service_type="service:test_%s" %(name)
			self._service_type="service:test2"
		   # self._service_port="12345"
		   # self._service_file_dir="%s/etc/slp/services" %(self._exp_root_dir) # !!!check this
		   # self._service_file_post=".service"
		   # self._service_name="svc-%s" % self._node_name
		
	def _generate_event(self, type, param, timestamp_given=0):
		'''
		This function generates an event, that is sent via RPC to the master 
		control program and is printed to the local event log file in the run directory
		of the initialised exeperiment.
		
		The sending function is executed in an own thread in order to quickly return
		from this funcation so it can be used in time critical places.
		@param this is an optional parameter. needed for example for the sd_find event to
		signal which service has been found
		'''
		if timestamp_given==0:
			ts = datetime.datetime.now()
		else:
			ts = timestamp_given
		ts_string = ts.isoformat(' ')
		
		if type==None:
			type = ""
		if param==None:
			param==""
			
		self.event_queue.put((self._node_name, ts_string, type, param))

		# log message to event log file (append)
		if self._file_event_log!=None:
			self._file_event_log.write("%s,%s,%s\n" %(ts_string, type, param))
		
		
	def _getStartTime (self):
		self._time1=datetime.datetime.now()   
		
#################################################################
# SD FUNCTIONS
#################################################################  


	# callback for findsrvs
	def srvcbSLP(self, srvurl, lifetime, errcode, cbdata):
		if errcode == slp.SLPError.SLP_OK:
			time2 = datetime.datetime.now()
			#nodeID = self.slph.findattrs(srvurl, ["nodeId"])[1]
			print "Started Search at time", self._time1
			print "Found Service: at time", time2
			#print "nodeID = ", nodeID
			path = slp.parsesrvurl(srvurl)[4]
			pathsplit = path.split("/")
			nodeName = pathsplit[2]
			self._generate_event("sd_service_add",nodeName,time2)
			cbdata[1].append((srvurl, time2))			
			#self._generate_event("sd_service_add",nodeID,time2)
		elif errcode == slp.SLPError.SLP_LAST_CALL:
			pass
		else:
			cbdata[0].errcode = errcode
			print "errcode = ", errcode
			return slp.SLP_FALSE
		return slp.SLP_TRUE

	def SD_search_thread(self):
		'''
		the thread running when search is active, it is reading from the browse subprocess
		'''
		print "SD_search_thread"
		sys.stdout.flush()
		ret = 0
		if self._sdp_type.lower() == "slp":

			cbdata = [ slp.SLPError.SLP_OK, [] ]
			self._getStartTime()
			self._generate_event("sd_start_search","",self._time1)
			self.slph.findsrvs(self._service_type, "", "default", self.srvcbSLP, cbdata )

			if cbdata[0] != slp.SLPError.SLP_OK:
				print "SLP Error "
				raise slp.SLPError(cbdata[0])
		

		else:
			cmd = "%s/usr/bin/avahi-browse -p %s" % (self._exp_root_dir , self._service_type)
			
			args = shlex.split(cmd)
			print "executing ", cmd
			self._browser_process = subprocess.Popen(args, bufsize=0, preexec_fn=self._getStartTime(), stdout=subprocess.PIPE)
			self._generate_event("sd_start_search","",self._time1)
			while True:
				try:
					line = self._browser_process.stdout.readline()
				except AttributeError:
					print "No Service Found"
					break
				#result=self._browser_process.communicate("")
				time2 = datetime.datetime.now()
			
			#if result[0] != '': !!!!!!!!! UPDATING HERE
				if line != '':                    
	#               if result[0].find("+")!=-1 and result[0].find("%s" % self._service_type)!=-1:
					if line[0]=='+' and line.find("%s" % self._service_type)!=-1:                                        
						#the real code does filtering here
						print "Started Search at time", self._time1
						print "Found Service: at time", time2
						#delta=time2-self._time1
						#delay=delta.days*86400*1000+delta.seconds*1000+(delta.microseconds/1000)
						#ret = [ self._time1.isoformat(' ') , time2.isoformat(' '), delay ]
						s=line.split(";")    
						self._generate_event("sd_service_add",s[3],time2)
						#self._browser_process.kill()
						#self._browser_process.wait()
						#self._browser_process = None
					if line[0]=='-' and line.find("%s" % self._service_type)!=-1:                                        
						#the real code does filtering here
						print "Started Search at time", self._time1
						print "Removed Service: at time", time2
						s=line.split(";") 
						#delta=time2-self._time1
						#delay=delta.days*86400*1000+delta.seconds*1000+(delta.microseconds/1000)
						#ret = [ self._time1.isoformat(' ') , time2.isoformat(' '), delay ] 
						self._generate_event("sd_service_del",s[3],time2)
						break  
		return ret
	
	def SD_init(self):
		'''
		Here everything should be done to prepare a clean run
		'''
		print "SD_init"
		sys.stdout.flush()	
		if self.experiment_inited == 0:
			return -1
		if self.sd_daemon_running == 1:
			return 
		
		print "Initialising SD"    
		if self._sdp_type.lower() == "slp":
			kill_and_wait("slpd")
			print "Killed all old SLPD-daemons!"
			self._cleanup_service(self._sdp_type)
			cmd = "%s/usr/sbin/slpd -l %s/etc/slpd/services/slpd-%s.log -c  %s/etc/slpd/config/slp-%s.conf" % ( self._exp_root_dir, self._exp_root_dir, self._node_name, self._exp_root_dir, self._node_name) 
			slp_env = os.environ
			slp_env["LD_LIBRARY_PATH"]="%s/usr/lib" % self._exp_root_dir
			args = shlex.split(cmd)
			self._daemon_process = subprocess.Popen(args, env=slp_env, bufsize=-1, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

			# !!!!!!!! a delay is required here so the daemon starts correctly before pubish. 
			time.sleep(3)
			# !!!!!!! the following is to check that daemon started. If the following is uncommented then the delay is not needed
			#cmd = "%s/usr/bin/slptool findsrvs service:service-agent" % self._exp_root_dir # 
			#slp_env = os.environ
			#slp_env["LD_LIBRARY_PATH"]="%s/usr/lib" % self._exp_root_dir
			#args = shlex.split(cmd)
			#self._daemonchk_process = subprocess.Popen(args, env=slp_env, bufsize=-1, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


			#line = self._daemonchk_process.stdout.readline()
			
			#if line == '':
			#	print "SLPD Daemon not started due to an error"
			#	return -1  
			#self._daemonchk_process.kill()
			print "SLPD Daemon started!"

			self.slph = slp.open()
			print "SLP handle set!"
			
		else:
			kill_and_wait("avahi-daemon")
			print "Killed all old Avahi-daemons!"
			self._cleanup_service(self._sdp_type)
			cmd = "%s/usr/sbin/avahi-daemon -f %s/etc/avahi/avahi-daemon.conf" % ( self._exp_root_dir, self._exp_root_dir)      
			avahi_env = os.environ
			avahi_env["LD_LIBRARY_PATH"]="%s/usr/lib" % self._exp_root_dir
			args = shlex.split(cmd)
			self._daemon_process = subprocess.Popen(args, env=avahi_env, bufsize=-1, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
			
			while True:
				line = self._daemon_process.stdout.readline()
				if line != '':
					if line.find("Server startup complete.")!=-1:
						break
					if line.find("exiting")!=-1:
						print "Avahi Daemon not started due to an error"
						return -1
					
			print "Avahi Daemon started!"
		self._generate_event("sd_init_done", "success")
		self.sd_daemon_running = 1
		return 0
	
	def SD_exit(self):
		print "SD_exit"
		sys.stdout.flush()
		if self.sd_daemon_running == 0:
			return 0
		if self.sd_search_running == 1:
			self.SD_stop_search()
		if self.sd_publish_running == 1:
			self.SD_unpublish()    
		print "stopping SD"
		if self._sdp_type.lower() == "slp":
			self.slph.close
		if self._daemon_process!=None:
			print "Killing Daemon"
			self._daemon_process.kill()
			if self._daemon_process != None:
				self._daemon_process.wait()
			self._daemon_process = None
		self.sd_daemon_running = 0
		self._generate_event("sd_exit_done", "success")
		return 0
	
	def SD_publish(self):
		''' Announces one service ID
		Set and forget...
		'''
		print "SD_publish"
		sys.stdout.flush()
		if self.sd_daemon_running == 0:
			print "Error: SD daemon not running"
			return -1

		if self.sd_publish_running ==1:
			print "Error: SD pubilish already running"
			return 0
		print "publishing service"
		##### publisher way ######
		#cmd = "%s/bin/avahi-publish -s %s _test-%s._udp %s" % (self._avahi_root_dir, self._service_name, ID, self._service_port)
		#args = shlex.split(cmd)
		#self._publish_process[ID] = subprocess.Popen(args)
		###########################
		##### service file way
		if self._sdp_type.lower() == "slp":
			self.slph.register(self._service_slp_url, 65535, self._service_slp_attrs) 
		else:
			filename="%s/service%s" % (self._service_file_dir, self._service_file_post)
			print "opening service file %s" % filename
			FILE = open(filename, "w")
			FILE.write("<?xml version=\"1.0\" standalone='no'?><!--*-nxml-*--><!DOCTYPE service-group SYSTEM \"avahi-service.dtd\">")
			FILE.write("<service-group><name replace-wildcards=\"yes\">%h</name>")
			FILE.write("<service protocol=\"ipv4\"><type>%s</type><port>%s</port></service>" % (self._service_type, self._service_port))
			FILE.write("</service-group>")
			FILE.close()
			print "Reloading avahi params"
			cmd = "%s/usr/sbin/avahi-daemon --reload" % self._exp_root_dir
			avahi_env = os.environ
			avahi_env["LD_LIBRARY_PATH"]="%s/usr/lib" % self._exp_root_dir
			args = shlex.split(cmd)
			subprocess.Popen(args, env=avahi_env, bufsize=-1)#, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		 
		#time.sleep(5)
		#this sleep is needed because the daemon will send out cache flush messages for 4 seconds after
		#establishing its service name
		self.sd_publish_running = 1
		self._generate_event("sd_start_publish", "success")
		return 0
	
	def SD_unpublish(self):
		''' Removes the service  '''
		print "SD_unpublish"
		if self.sd_daemon_running == 0:
			return -1
		if self.sd_publish_running == 0:
			return 0
		print "Removing published service"
		# publisher way 
		#self._publish_process[ID].kill()
		if self._sdp_type.lower() == "slp":
			self.slph.deregister(self._service_slp_url)
		else:
		# service file way
			file = "%s/%s" % (self._service_file_dir, self._service_file_post)
			if os.path.exists(file ):
				os.remove(file)
				cmd = "%s/usr/sbin/avahi-daemon --reload" % self._exp_root_dir
				avahi_env = os.environ
				avahi_env["LD_LIBRARY_PATH"]="%s/usr/lib" % self._exp_root_dir
				args = shlex.split(cmd)
				subprocess.Popen(args, env=avahi_env, bufsize=-1, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		self.sd_publish_running = 0
		self._generate_event("sd_stop_publish", "success")
		return 0
	
	def SD_start_search(self):
		'''
		Searches for the service with ID as in setup.
		@return array of three strings representing timestamp before and after search and the delay in ms 
		'''
		print "SD_start_search"
		sys.stdout.flush()
		if self.sd_daemon_running == 0:
			return -1
		if self.sd_search_running == 1:
			return 0  
		print "Starting search"
		thread.start_new_thread(self.SD_search_thread, ())
		self.sd_search_running = 1
		return 0
	   
	def SD_stop_search(self):
		'''
		Stops the search
		'''
		print "SD_stop_search"
		sys.stdout.flush()
		if self.sd_daemon_running == 0:
			return -1
		if self.sd_search_running == 0:
			return 0
		print "Stopping search"
		if self._browser_process!=None:
			print "Killing Browser"
			self._browser_process.kill()
			self._browser_process.wait()
			self._browser_process = None
		self.sd_search_running = 0
		self._generate_event("sd_stop_search", "success")
		return 0
	

#################################################################
# CAPTURE FUNCTIONS
#################################################################
	def capture_start(self):
		'''
		starts a new capture. 
		BLOCKS until capturing has started!
		'''
		print "capture_start"
		if self.capture_running == 1:
			return 0
		
		if self._current_run_role != "actor":
			return 0
		
		print "starting capture"
		
		# now start capture
		#
		if self._sdp_type.lower() == "slp":
			self._capture_filename_mainIf="%s_%s.pcap" % (self._node_name, self._cap_interface)
			self._cap_file_mainIf="%s/%s" % (self._capture_dir, self._capture_filename_mainIf)
			cmd = "touch %s" % self._cap_file_mainIf
			args = shlex.split(cmd)
			p=subprocess.Popen(args)
			p.wait()

			#print "Capturing on %s into file %s" % (self._cap_interface,cap_file)
			os.chown(self._cap_file_mainIf, self._uid, self._gid)

			self._capture_filename_wlan2="%s_wlan2.pcap" % self._node_name     
			self._cap_file_wlan2="%s/%s" % (self._capture_dir, self._capture_filename_wlan2)
			cmdw = "touch %s" % self._cap_file_wlan2
			argsw = shlex.split(cmdw)
			pw=subprocess.Popen(argsw)
			pw.wait()

			#print "Capturing on %s into file %s" % (self._cap_interface,cap_file)
			os.chown(self._cap_file_wlan2, self._uid, self._gid)
			#print "\tstart Capture"
			command_line = 'tshark -i %s -f "udp port 427" -w "%s"' % (self._cap_interface, self._cap_file_mainIf)
			args = shlex.split(command_line)			
			self._capture_process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
			while True:
				line = self._capture_process.stdout.readline()
				print line
				if line != '':
					# wait until avahi says its ready"#
					if line.find("Capturing on")!=-1:
						break

			command_line = 'tshark -i wlan2 -f "udp port 427" -w "%s"' % (self._cap_file_wlan2)
			args = shlex.split(command_line)			
			self._capture_process_wlan = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

			while True:
				line = self._capture_process_wlan.stdout.readline()
				print line
				if line != '':
					# wait until avahi says its ready"#
					if line.find("Capturing on")!=-1:
						break
			
			
		#	print "\tExecuting %s" % command_line
		else:
			self._capture_filename="%s.pcap" % self._node_name     
		# bug workaround: we have to create the file before using it
			cap_file="%s/%s" % (self._capture_dir, self._capture_filename)
			cmd = "touch %s" % cap_file
			args = shlex.split(cmd)
			p=subprocess.Popen(args)
			p.wait()

			#print "Capturing on %s into file %s" % (self._cap_interface,cap_file)
			os.chown(cap_file, self._uid, self._gid)
			command_line = r'tshark -i %s -f "udp port 5353" -w "%s"' % (self._cap_interface, cap_file)
			args = shlex.split(command_line)
			#print "\tExecuting %s" % command_line
			self._capture_process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		# wait for startup
			while True:
				line = self._capture_process.stdout.readline()
				print line
				if line != '':
					# wait until avahi says its ready"#
					if line.find("Capturing on")!=-1:
						break
					
		print "\tCapture started and running the background."
		self.capture_running=1
		return 0
	
	def capture_stop(self):
		'''
		stops capture
		'''
		print "capture_stop"
		if self.capture_running==0:
			return 0
		if self._current_run_role != "actor":
			return 0
		print "stopping capture"
		if self._capture_process!=None:
			cmd = "sudo killall -q dumpcap"
			args = shlex.split(cmd)
			p = subprocess.Popen(args)
			cnt = 0
			while (not p.poll()) and cnt<3:
				time.sleep(0.3)
				cnt = cnt + 1
				
			print "Killing Capture"
			self._capture_process.kill()
			self._capture_process.wait()
			self._capture_process = None
			if self._sdp_type.lower() == "slp":
				self._capture_process_wlan.kill()
				self._capture_process_wlan.wait()
				self._capture_process_wlan = None
			print "\tKilling Capture subprocess dumpcap"
			time.sleep(0.1)
			# dumpcap is a child of tshark which doesn't get killed when tshark is killed
			if self._sdp_type.lower() == "slp":
				cmdw = "editcap -w 0.005 %s %s" % (self._cap_file_wlan2, self._cap_file_wlan2)
				argsw = shlex.split(cmdw)
				pw=subprocess.Popen(argsw)
				pw.wait()
				cmdw = "editcap -w 0.005 %s %s" % (self._cap_file_mainIf, self._cap_file_mainIf)
				argsw = shlex.split(cmdw)
				pw=subprocess.Popen(argsw)
				pw.wait()
			self.capture_running=0
		return 0

#################################################################
# TRAFFIC GENERATOR FUNCTIONS
#################################################################    
	def traffic_start(self, servernode, bandwidth):
		print "traffic_start for %s" %(servernode)
		#create new logfile 
		n = len(self.iperf_client_logfiles[servernode])
		outfile = "%s/iperf_client_%s_%s_%d.log"%(self._env_dir,self._node_name,servernode,n)
		self.iperf_client_logfiles[servernode].append(open(outfile,'w'))
		cmd = "iperf -u -t 14400 -i 5 -c %s-%s -b %dk" % (servernode,self._traffic_interface,bandwidth)
		#cmd = "iperf -u -t 14400 -i 5 -c %s-wlan0 -b %d 1>>~/Logs/iperf/iperf_%s_c 2>&1 &" % (servernode,bandwidth,self._nodename) 
		args = shlex.split(cmd)
		#print "Starting traffic with: %s" % cmd
		self.iperf_client_processes[servernode].append(subprocess.Popen(args,stdout=self.iperf_client_logfiles[servernode][-1]))
		#print "\tIperf client started"
		self._generate_event("traffic_start", "%dk"%bandwidth)
		return 0

	def traffic_stop_all(self):
		print "traffic_stop_all"
		if len(self.iperf_client_processes)>0:
			print "stopping all traffic"
			for i in self.iperf_client_processes:
				for process in self.iperf_client_processes[i]:
					if process!=None:
						try:
							process.kill()
							process.wait()
						except:
							print "exception while killing iperf"
					process = None
			self.iperf_client_processes=defaultdict(list)

			for j in self.iperf_client_logfiles:
				for log in self.iperf_client_logfiles[j]:
					if log!=None:
						try:
							log.close()
						except:
							print "exception closing logfile of iperf for node %s" %(servernode)
							pass
					log = None
			self.iperf_client_logfiles = defaultdict(list)
		self._generate_event("traffic_stop_all", "")
		return 0

	def traffic_stop(self,servernode):
		print "traffic_stop" 
		if len(self.iperf_client_processes)>0:
			
			if servernode in self.iperf_client_processes:
				print "stopping traffic for %s" %(servernode)
				
				if self.iperf_client_processes[servernode]!=[]:
					try:
						#Since we might have multiple instances, just eliminate the first one
						self.iperf_client_processes[servernode][0].kill()
						self.iperf_client_processes[servernode][0].wait()
					except:
						print "exception while killing iperf for node %s" %(servernode)
				
					try:
						self.iperf_client_logfiles[servernode][0].close()
					except:
						print "exception closing logfile of iperf for node %s" %(servernode)
						pass
		self._generate_event("traffic_stop", "%s"%servernode)
		return 0

	
	def traffic_update(self, servernode, bandwidth):
		self.traffic_stop(servernode)
		self.traffic_start(servernode, bandwidth)
		
################################################################
# FAULT INJECTION & NETWORK MANAGEMENT
################################################################
	def fail_start_drop_sd(self):
		'''
		Drops pakets of the used sdp
		'''
		print "fail_start_drop_sd"
		if self.state_dropping==1:
			return 0
		#Port comes from OLSR BMF plugin that encapsulates IP packets to keep forwarder address
		port = "50698"
		args = shlex.split("sudo iptables -I INPUT -p udp --dport 50698 -j DROP" )
		p0=subprocess.Popen(args)
		p0.wait()
		args = shlex.split("sudo iptables -I OUTPUT -p udp --dport 50698 -j DROP" )
		p1=subprocess.Popen(args)
		p1.wait()
		args = shlex.split("sudo iptables -I FORWARD -p udp --dport 50698 -j DROP" )
		p2=subprocess.Popen(args)
		p2.wait()
		# Drop also srvloc port 427 for SLP experiments
		args = shlex.split("sudo iptables -I INPUT -p udp --dport 427 --sport 427 -j DROP" )
		p0=subprocess.Popen(args)
		p0.wait()
		args = shlex.split("sudo iptables -I OUTPUT -p udp --dport 427 --sport 427 -j DROP" )
		p1=subprocess.Popen(args)
		p1.wait()
		args = shlex.split("sudo iptables -I FORWARD -p udp --dport 427 --sport 427 -j DROP" )
		p2=subprocess.Popen(args)
		p2.wait()
		self.state_dropping = 1
		self._generate_event("fail_start_drop_sd", "")
		return 0
	
	
	def fail_stop_drop_sd(self):
		print "fail_stop_drop_sd"
		# remove in anc case
		#if self.state_dropping==0:
		#    return 0
		port = "50698"
		args = shlex.split("sudo iptables -D INPUT -p udp --dport 50698 -j DROP" )
		p0=subprocess.Popen(args)
		p0.wait()
		args = shlex.split("sudo iptables -D OUTPUT -p udp --dport 50698 -j DROP" )
		p1=subprocess.Popen(args)
		p1.wait()
		args = shlex.split("sudo iptables -D FORWARD -p udp --dport 50698 -j DROP" )
		p2=subprocess.Popen(args)        
		p2.wait()
		args = shlex.split("sudo iptables -D INPUT -p udp --dport 427 --sport 427 -j DROP" )
		p0=subprocess.Popen(args)
		p0.wait()
		args = shlex.split("sudo iptables -D OUTPUT -p udp --dport 427 --sport 427 -j DROP" )
		p1=subprocess.Popen(args)
		p1.wait()
		args = shlex.split("sudo iptables -D FORWARD -p udp --dport 427 --sport 427 -j DROP" )
		p2=subprocess.Popen(args)        
		p2.wait()
		self.state_dropping = 0
		self._generate_event("fail_stop_drop_sd", "")
		return 0
		
	def failure(self):
		return 0
		
	def system_monitor(self):
		return 0
		
#################################################################
# OLSR information gathering
#################################################################
	def get_olsr(self):
		''' Gets OLSR information  '''
		print "getting_olsr"
		cmd = ["/bin/bash","bin/links-info.sh", "%s/%s.json" % (self._links_dir,     self._node_name)]
		
		p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
		# Get metrics
		p.communicate()
		sys.stdout.flush()
		p.wait()
		self._generate_event("getting_olsr", "")
		return 0

#################################################################
# TESTING FUNCTIONS
#################################################################
	def sleep(self, t):
		self.sleep_counter = self.sleep_counter+1
		print "SLeeping for the %d. time" % self.sleep_counter
		time.sleep(t)
		return 0
		
		
		 
if __name__ == '__main__':
	global kill_threads
	stat= os.stat("./Node_ManagerRPC.py")
	print "Node_ManagerRPC %s starting" % str(stat.st_mtime)
	kill_threads = 0

	# Create server 
	#'' means bind to all addresses
	expNode=ExpNodeManager()
	server = SimpleXMLRPCServer(('', 8000),requestHandler=RequestHandler, allow_none=True)
	server.register_introspection_functions()
	server.register_instance(expNode)
	expNode.event_queue = Queue.Queue()
	event_thread = event_sender_thread(expNode.event_queue)
	event_thread.start()
	################
	# Automatically detect which user is running this script as
	# root using sudo.
	# Files are created with the original users uid and gid
	#if os.getenv("SUDO_UID")==None:
	#    expNode._uid=int(os.getuid())
	#    expNode._gid=int(os.getgid())
	#else:
	#expNode._uid=1044
	#expNode._gid=1047


	expNode._uid=int(os.getenv("SUDO_UID")) # 1017
	expNode._gid=int(os.getenv("SUDO_GID")) #1019
	
	# Run the server's main loop
	try:
		server.serve_forever()
	except (KeyboardInterrupt, SystemExit):
		
		expNode.run_exit()
		expNode.experiment_exit()
		kill_threads=1
		print "Program was terminated by CTRL+C"
