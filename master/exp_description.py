import xml.dom.minidom as dom
import time
from xml.dom import Node
import optparse
import os
import sys
import random
import threading


################################################################################
################################################################################

class actor_node_map:
	'''
	Reads the <actor_node_map> element and creates an internal representation
	using a list (actors by id) of lists(instances by id) of abstract Node names
	#
	
	
	'''
	#actor_list = None
	
	def __init__(self, XMLactor_node_map):
		self.actor_list = {}
		for actor in XMLactor_node_map.getElementsByTagName("actor"):
			self.instance_list = {}
			for instance in actor.getElementsByTagName("instance"):
				self.instance_list[instance.getAttribute("id")] = instance.firstChild.data
			self.actor_list[actor.getAttribute("id")] = self.instance_list
	
	def get_num_of_actors(self):
		return len(self.actor_list)
	
	def get_abstract_node(self, aid, iid):
		return self.actor_list[aid][iid]
	
	def get_actor_id(self, num):
		i = 0
		for aid,instances in self.actor_list.items():
			if i == num:
				return aid
			i = i + 1
		return -1
	
	def contains_abstract_node(self, abstract_node):
		'''
		returns true, if the abstract node id
		is in the current mapping
		'''
		for aid,instances in self.actor_list.items():
			for iid, node in instances.items():
				if node == abstract_node:
					return True
		return False
		
	def get_instance_id(self, aid, num):
		i = 0
		for iid,node in self.actor_list[aid].items():
			if i == num:
				return iid
			i = i + 1
		return -1
	
	def get_instance(self, aid, num):
		i = 0
# 		print self.actor_list[aid].items()
		for iid,node in self.actor_list[aid].items():
# 			print "iid %s" % iid
# 			print "node %s" % node
			if i == num:
				return node
			i = i + 1
		return -1
	
	def get_abstract_node(self, aid, iid):
		inst = self.actor_list[aid]
		return inst[iid]
	
	def get_abstract_nodes(self, aid, iid):
		'''
		returns a list of nodes when iid=="all", else
		a list with one element
		'''
		result = []
		if aid=="all":
			raise Exception
		
		if iid=="all":
			inst = self.actor_list[aid]
# 			print inst
			for (id,name) in inst.items():
				result.append(name)
		else: 
			result.append(self.actor_list[aid][iid])
		return result
		
	
	def get_num_of_instances(self, aid):
		return len(self.actor_list[aid])
	
	def get_num_of_total_instances(self):
		i = 0
		for aid,instances in self.actor_list.items():
			for iid,node in instances.items():
				i = i + 1
		return i
	
	def summary(self):
		s = "\n"
		for aid,instances in self.actor_list.items():
			for iid,node in instances.items():
				s = "%s%s" %(s,"\t\tactor %s, instance %s in mapped to node %s" %(aid,iid, node))
			s = "%s\n" % s
		return s

class exp_parameter:
	'''
	This class contains only two values:
	type: this can be either fixed or reference
	data: this is either the parameter (of any type) or the factor_id
	'''
	def __init__(self, type, data):
		self.type = type
		self.data = data
	
################################################################################
################################################################################

class exp_factor_levels:
	'''
	This class generates a list
	of levels for one factor.
	The data has a type
	'''
	#level_list = None
	#type = None
	def __init__(self, type, XMLlevels):
		self.level_list = []
		self.type	   = type
		for lvl in XMLlevels:
			if type=="int":
				self.level_list.append(int(lvl.firstChild.data))
			if type=="actor_node_map":
				self.level_list.append(actor_node_map(lvl))
				
	def get_len(self):
		return len(self.level_list)
	
	def get_levels(self):
		return self.level_list
	
	def get_level(self, levelnum):
		return self.level_list[levelnum]
	
	def summary(self):
		print "factor_levels"
		i = 0
		for lvl in self.level_list:
			if self.type == "int":
				print "\t level %d = %d"%(i,lvl)
			if self.type == "actor_node_map":
				print "\t level %d = %s" % (i,lvl.summary())
			i = i + 1

################################################################################
################################################################################
   
class exp_factor:
	def __init__(self, id, type, levels, usage,description):
		self.id = id
		self.type = type
		self.levels = levels
		self.usage = usage
		self.description = description

	def get_level(self, levelnum):
		return self.levels.get_level(levelnum)
	 
	def summary(self):
		print "Factor "
		print "\t type=%s" %(self.type)
		print "\t id=%s is used %s" %(self.id, self.usage)
		print "\t description=\"%s\"" %(self.description)
		print "\t has %d levels" % (self.levels.get_len())
		self.levels.summary()

		
################################################################################
################################################################################

class exp_action:
	action_types = ["sd_init", "sd_exit", "sd_publish", 
					"sd_unpublish", "sd_start_search",
					"sd_stop_search", "wait_for_event",
					"wait_marker", "wait_time",
					"fault_start_interface_fail",
					"fault_stop_interface_fail",
					"env_traffic_start", "env_traffic_stop",
					"env_traffic_update",
					"fault_start_drop_sd","fault_stop_drop_sd",
					"get_olsr",
					"event_flag","env_start_drop_sd", "env_stop_drop_sd"]
	#action = ""
	#parameter_list = {} #key/value
	def __init__(self, XMLaction):
		self.parameter_list = {}
		if self._check_type(XMLaction)==False:
			raise Exception
		self.action = XMLaction.nodeName
		self.get_parameters(XMLaction, self.parameter_list)
			
	def _check_type(self, XMLaction):
		'''
		checks, if a given (xml) action is available
		'''
		for i in self.action_types:
			if XMLaction.nodeName==i:
				return True	 
		print "did not find type", XMLaction.nodeName	
		return False
	
	def get_parameters(self, XMLaction, parameter_list):
		'''
		parses the xml into a parameter list, 
		each parameter value can also be a ref
		'''
		for params in XMLaction.childNodes:
			if params.nodeType==Node.TEXT_NODE:
				continue

			ref = params.getElementsByTagName("factorref")
			if len(ref)==0:
				type = "fix"
				data = params.firstChild.data
				node_param = params.getElementsByTagName("node")
				if len(node_param)>0:
					# we have a node parameter here...
					data = {}
					data["actor"]=node_param[0].getAttribute("actor")
					data["instance"]=node_param[0].getAttribute("instance")
					
			else:
				type = "ref"
				data = ref[0].getAttribute("id")
			
			parameter_list[params.nodeName] = exp_parameter(type,data)
		
			
	def summary(self):
		print "\t  %s" % self.action
		for (name,param) in self.parameter_list.items():
			print "\t param %s is %s and value is %s" %(name,param.type,param.data)
		
		
class exp_actor:
	'''
	This class represents the actors that contains the actions for sd and fault threads
	'''
	def __init__(self, XMLexp_actor ):
		self.name = XMLexp_actor.getAttribute("name")
		self.id   = XMLexp_actor.getAttribute("id")
		self.sd_action_list	= []
		self.fault_action_list = []
		
		# build abstract actors for sd actions
		actions = XMLexp_actor.getElementsByTagName("sd_actions")
		for action in actions[0].childNodes:
			if action.nodeType == Node.TEXT_NODE:
				continue
			try:
				exp_act = exp_action(action)
			except Exception:
				print "Error in action definition (%s)" % action.nodeName
				raise
			self.sd_action_list.append(exp_act)
		
		# build abstract actors for fault actions
		actions = XMLexp_actor.getElementsByTagName("fault_actions")
		if len(actions)!=0:
			for action in actions[0].childNodes:
				if action.nodeType == Node.TEXT_NODE:
					continue
				try:
					exp_act = exp_action(action)
				except Exception:
					print "Error in action definition (%s)" % action.nodeName
					raise
				self.fault_action_list.append(exp_act)
				
	def has_fault_actions(self):
		if len(self.fault_action_list)!=0:
			return True
		else:
			return False
			
		
	def summary(self):
		print "abstract actor"
		print "\t id=%s name=\"%s\"" % (self.id,self.name) 
		print "\t number of sd_actions = %d" % (len(self.sd_action_list))
		for i in self.sd_action_list:
			i.summary()
		print "\t number of fault_actions = %d" % (len(self.fault_action_list))
		for i in self.fault_action_list:
			i.summary()	
			
class exp_env_process:
	'''
	This class represents the environment process, which
	does global manipulations that are unspecific to the nodes
	that take part in service discovery
	'''
	
	def __init__(self, XMLenv_process):
		'''
		This function reads the DOM element env_process and
		creates a local representation for it
		'''
		self.description = XMLenv_process.getElementsByTagName("description")[0].firstChild.data
		self.action_list = []
		
		# build abstract actors
		actions = XMLenv_process.getElementsByTagName("env_actions")
		for action in actions[0].childNodes:
			if action.nodeType == Node.TEXT_NODE:
				continue
			try:
				exp_act = exp_action(action)
			except Exception:
				print "Error in action definition (%s)" % action.nodeName
				raise
			self.action_list.append(exp_act)
			
	def summary(self):
		print "env process (actor)"
		print "\t description: %s" %(self.description)
		print "\t number of env_actions = %d" % (len(self.action_list))
		for i in self.action_list:
			i.summary()

class exp_global_process:
	'''
	This class represents the global process, which
	does manipulations that are constant along all the experiment
	runs
	'''
	
	def __init__(self, XMLenv_process):
		'''
		This function reads the DOM element global_process and
		creates a local representation for it
		'''
		self.description = XMLenv_process.getElementsByTagName("description")[0].firstChild.data
		self.action_list = []
		
		# build abstract actors
		actions = XMLenv_process.getElementsByTagName("global_actions")
		for action in actions[0].childNodes:
			if action.nodeType == Node.TEXT_NODE:
				continue
			try:
				exp_act = exp_action(action)
			except Exception:
				print "Error in action definition (%s)" % action.nodeName
				raise
			self.action_list.append(exp_act)
			
	def summary(self):
		print "global process (actor)"
		print "\t description: %s" %(self.description)
		print "\t number of global_actions = %d" % (len(self.action_list))
		for i in self.action_list:
			i.summary()
	
	
class exp_node_processes:
	''' 
	This class reflects the acting node with
	its steps and parameters.
	'''
	#actor_list = None
	#actor_node_map = None
	
	def __init__(self,XMLnode_processes):
		'''
		@param_mapping is of exp_parameter type (contains type and data field)
		'''
		self.actor_list =  []
		
		self.name = XMLnode_processes.getAttribute("name")		
		
		# find out what the parameter is
		params = XMLnode_processes.getElementsByTagName("process_parameters")
		an_mapping = params[0].getElementsByTagName("actor_node_map")
		ref = an_mapping[0].getElementsByTagName("factorref")
		if len(ref)!=0:
			param_type = "ref"
			param_data = ref[0].getAttribute("id")
		else:
			param_type = "fix"
			param_data = actor_node_map(an_mapping[0])
		
		self.param_mapping = exp_parameter(param_type, param_data)
		
		actors = XMLnode_processes.getElementsByTagName("actor")
		for a in actors:
			actor = exp_actor(a)	 
			self.add_actor(actor)
	
	def add_actor(self, new_actor):
		self.actor_list.append(new_actor)
		
	def get_actor(self, aid):
		for actor in self.actor_list:
			if actor.id == aid:
				return actor
		return None
	
	def summary(self):
		print "Node Processes"
		print "\t has name \"%s\"" %(self.name)
		print "\t mapping is: %s, %s " %(self.param_mapping.type,self.param_mapping.data)
		print "\t has %d actors" %(len(self.actor_list))
		for a in self.actor_list:
			a.summary()

################################################################################
################################################################################
	
def walk_and_remove_comments(node):
	if node.hasChildNodes():
		for child in node.childNodes:
			ret=walk_and_remove_comments(child)
			if ret==1:
				#print "Found comment \"%s\", removing it" %(child.data)
				node.removeChild(child)
				child.unlink()
				
	else:
		if node.nodeType==Node.COMMENT_NODE:
			return 1
		return 0


class factor_level_matrix():
	'''
	This class contains functions to create a matrix with the run definitions
	'''
	def __init__(self):
		pass
	# create a 2D matrix of zeros and populate it 
	def make_list(self, size):
		"""create a list of size number of zeros"""
		mylist = []
		for i in range(size):
			mylist.append(0)
		return mylist
	 
	def make_matrix(self, rows, cols):
		"""
		create a 2D matrix as a list of rows number of lists
		where the lists are cols in size
		resulting matrix contains zeros
		"""
		matrix = []
		for i in range(rows):
			matrix.append(self.make_list(cols))
		return matrix
	
	def fill_field(self, m, col, row, factor_list):
		if col==len(m[0])-1:
			if m[row-1][col]==factor_list[col].levels.get_len()-1:
				m[row][col]=0
				return 1
			else:
				m[row][col]=m[row-1][col]+1
				return 0
		else:
			if self.fill_field(m, col+1,row, factor_list)==1:
				if m[row-1][col]==factor_list[col].levels.get_len()-1:
					m[row][col]=0
					return 1
				else:
					m[row][col]=m[row-1][col]+1
					return 0
			else:
				m[row][col]=m[row-1][col]
				return 0
	
	def print_matrix(self, m):
		for i in range(len(m)):
			print m[i]
			
	def fill_matrix(self, m, factor_list):
		y = 1
		while(y<len(m)):
			self.fill_field(m, 0, y, factor_list)
			y = y + 1
	
	def make_run_identifier(self, run_definition):
		s = "run"
		for i in run_definition:
			s = "%s_%d" % (s,i)
		#return "%s%s" % (time.strftime("%y%m%d-%H%M%S",time.localtime()), s)
		return s

class exp_platform_spec:
	'''
	This class parses a <platform_specs> element
	This includes creating a node list
	
	This class holds the abstract nodes to real nodes mappings,
	defined by the experimenter for each experiment
	It contains also the "not experiment input" parameters that
	are fixed, or cannot be considered like topology
	'''
	def __init__(self, platform_specs_element):
		self.actor_map = []
		self.env_map   = []
		
		description = platform_specs_element.getElementsByTagName("description")
		self.description = description[0].firstChild.data
		
		spec_node_mapping = platform_specs_element.getElementsByTagName("spec_node_mapping")
		for map in spec_node_mapping[0].getElementsByTagName("spec_actor_map"):
			abstract_id = str(map.getAttribute("abstract_id"))
			real_id = str(map.getAttribute("id"))
			real_ip = str(map.getAttribute("ip"))
			self.actor_map.append( {'abstract_id':abstract_id,'real_id':real_id,'real_ip':real_ip})
		
		for map in spec_node_mapping[0].getElementsByTagName("spec_env_map"):
			real_id = str(map.getAttribute("id"))
			real_ip = str(map.getAttribute("ip"))
			self.env_map.append( {'real_id':real_id,'real_ip':real_ip,'abstract_id':''})

	def get_actor_map(self):
		return self.actor_map
	def get_env_map (self):
		return self.get_env_map()
	def summary(self):
		'''
		prints out the mappings
		'''
		print "Platform specifics"
		print "Actor nodes:"
		for a in self.actor_map:
			print "\t%s\t%s\t%s"%(a['abstract_id'],a['real_id'],a['real_ip'])
		print "Env nodes:"
		for e in self.env_map:
			print "\t%s\t%s"%(e['real_id'],e['real_ip'])
			

	
class experiment_description:
	'''
	This class represents the contents of the xml experiment description.
	The file is once parsed and then all the parameters can be used in the 
	experiment.
	'''
	factor_list = None
	abstract_nodes_name = None
	node_processes = None
	actor_list = None
	factor_id_list = None;

	def __init__(self, xmlfile):
		self.factor_list = []
		self.abstract_nodes_name = []
		self.factor_list = []
		self.factor_id_list =[];
		
		tree = dom.parse(xmlfile)
		
		walk_and_remove_comments(tree)
		self.max_run_time = int(tree.getElementsByTagName("processes")[0].getAttribute("max_run_time"))
		
		#abstract nodes
		abstractnodelist = tree.getElementsByTagName("abstractnodes")
		self.number_of_abstract_nodes = len(abstractnodelist[0].getElementsByTagName("abstractnode"))
		for node in abstractnodelist[0].getElementsByTagName("abstractnode"):
			self.abstract_nodes_name.append(node.getAttribute("id"))
		
		#node processes
		xml_node_processes = tree.getElementsByTagName("node_processes")
		self.node_processes = exp_node_processes(xml_node_processes[0])			
		
		#env process
		xml_env_process = tree.getElementsByTagName("env_process")
		self.env_process = exp_env_process(xml_env_process[0])
		
		#global process
		xml_global_process = tree.getElementsByTagName("global_process")
		if xml_global_process != []:
			self.global_process = exp_global_process(xml_global_process[0])
		
		#factors
		for factor in tree.getElementsByTagName("factor"):
			description = factor.getElementsByTagName("description")
			levels = factor.getElementsByTagName("level")
			type = factor.getAttribute("type")
			fac_lvls = exp_factor_levels(type,levels)
			fac = exp_factor(factor.getAttribute("id"),type, fac_lvls, factor.getAttribute("usage"),description[0].firstChild.data)
			self.factor_list.append(fac)
		#replication factor (auto generate sequence)
		replicationfactor = tree.getElementsByTagName("replicationfactor")
		if len(replicationfactor)==1:
			type=replicationfactor[0].getAttribute("type")
			num_of_replica = replicationfactor[0].firstChild.data
			s = "<levels>"
			for i in range(int(num_of_replica)):
				s = "%s<level>%d</level>" % (s,i)
			s = s+"</levels>"
			lvls=dom.parseString(s).getElementsByTagName("level")
			fac_lvls = exp_factor_levels(type,lvls)
			fac = exp_factor(replicationfactor[0].getAttribute("id"),type, fac_lvls, replicationfactor[0].getAttribute("usage"),"replication")
			self.factor_list.append(fac)
		



		#Create the encoding file
		Exp_Enc_f = open("Exp_Enc.xml","w+"); #Open the file for and overwrite 
		s='<!-- Number of factor = %d -->\n'%len(self.factor_list);
		Exp_Enc_f.write(s);
 		s= '<factor_list>\n';
 		Exp_Enc_f.write(s);
		#Factor representation in the Exp_Enc file
		'''<factor  id="fact_bw" index ="1" levels="72" >
		</factor>
		'''

		i =0;
		for factor in self.factor_list:
			i =i +1;
			s='\t<!-- Factor number %d --> \n' %(i);
			Exp_Enc_f.write(s);
			s='\t<factor id ="%s" index="%d" levels="%d" >' %(factor.id,i,factor.levels.get_len()) ;
			Exp_Enc_f.write(s);
			#s='\t\t<levels>%d</levels> \n' %factor.levels.get_len();
			#Exp_Enc_f.write(s);
			s='\t</factor>\n';
			Exp_Enc_f.write(s);
			Exp_Enc_f.write("\n");
		s= '</factor_list>';
		Exp_Enc_f.write(s);
		Exp_Enc_f.close();


		#name
		self.experiment_name = tree.getElementsByTagName("experiment_name")[0].firstChild.data

		#protocol
		self.sd_protocol = tree.getElementsByTagName("sd_protocol")[0].firstChild.data

		# create the factor level matrix for all runs
		self.factor_level_matrix=factor_level_matrix()
		self.run_matrix = None
		self.create_run_matrix()
		# load the platform specifics
		platform_specs = tree.getElementsByTagName("platform_specs")
		self.platform_specs = exp_platform_spec(platform_specs[0])
		
		# Reading requester from XML file
		requester_found = False
		# First check the SD actions for the abstract actor ID that is searching
		for processactor in self.node_processes.actor_list:
			for processactoraction in processactor.sd_action_list:
				if processactoraction.action == "sd_start_search":
					requester_found = True
					break
			if requester_found:
				requester_ID = processactor.id
				break

		# Now get the instance for that abstract actor ID
		for factors in self.factor_list:
			if factors.id == "fact_nodes":
				for cur_actor_id in range(factors.levels.get_level(0).get_num_of_actors()):
					if factors.levels.get_level(0).get_actor_id(cur_actor_id) == requester_ID:
						requester = factors.levels.get_level(0).get_instance(requester_ID, 0)
						break
				break
		
		# Finally get the real ID (= node name) of that instance
		for curactor in self.platform_specs.actor_map:
			if curactor["abstract_id"] == requester:
				requester_realID = curactor["real_id"]
				self.requester = curactor
				break
		
# 		print "Requester %s has ID %s and is node %s." % (requester_ID, requester, requester_realID)

		# Reading responders from XML file
		self.responders = []
		# First check the SD actions for the abstract actor ID that is publishing
		processactorids = []
		for processactor in self.node_processes.actor_list:
			for processactoraction in processactor.sd_action_list:
				if processactoraction.action == "sd_publish":
					processactorids.append(processactor.id)
		
		# Now get the instance for that abstract actor ID
		responders = []
		for processactorid in processactorids:
			for factors in self.factor_list:
				if factors.id == "fact_nodes":
					for cur_actor_id in range(factors.levels.get_level(0).get_num_of_actors()):
						if factors.levels.get_level(0).get_actor_id(cur_actor_id) == processactorid:
							for instancenum in range(factors.levels.get_level(0).get_num_of_total_instances()):
								responders.append(factors.levels.get_level(0).get_instance(processactorid, instancenum))
				break
		
		# Finally get the real ID (= node name) of that instance
		for responder in responders:
			for curactor in self.platform_specs.actor_map:
				if curactor["abstract_id"] == responder:
					responder_realID = curactor["real_id"]
					self.responders.append(curactor)
		
# 		print self.responders
# 		exit()

	
	def get_requester(self):
		'''
		Retrieves the requesting node for the current set of experiments
		'''
		return self.requester
	
	def get_responders(self):
		'''
		Retrieves the responding nodes for the current set of experiments
		'''
		return self.responders
	
	def get_factor_by_id(self, id):
		'''
		Retrieves a given @param id factor
		'''
		for factor in self.factor_list:
			if factor.id == id:
				return factor
		return None
	
	def get_factor_count(self):
		return len(self.factor_list)
	
	def actor_node_map_is_factor(self):
		'''
		utility function to know if the node mapping is a factor or a constant
		'''
		if self.node_processes.param_mapping.type=="ref":
			return True
		else:
			return False
	
	def get_actor_node_map_factor_id(self):
		return self.node_processes.param_mapping.data
	
	def summary(self):
		print "This design"
		print "\t uses %d abstract nodes" % ( self.number_of_abstract_nodes )
		for i in range(len(self.abstract_nodes_name)):
			print "\t abstract node %d is called %s" %(i,self.abstract_nodes_name[i])
		print "\t uses %d factors" % (len(self.factor_list ))
		for factor in self.factor_list:
			factor.summary()
		self.node_processes.summary()
		self.env_process.summary()
		print "Factor Level Assignment Plan:"
		#self.factor_level_matrix.print_matrix(self.run_matrix)
		self.platform_specs.summary()
		
	def create_run_matrix(self):
		#generate run sequence
		# [ ["id1": 0, "id2":0],
		#   ["id1": 1, "id2":0]...
		# ]
		
		# full factorial
		n = 1
		for fact in self.factor_list:
			n = n * fact.levels.get_len()
		#random.seed(0)
		#print range(len(exp.factor_list[1].levels.level_list))
		#print random.sample(range(len(exp.factor_list[1].levels.level_list)),exp.factor_list[1].levels.get_len())
		print "There must be %d runs" %n
		self.run_matrix = self.factor_level_matrix.make_matrix(n,len(self.factor_list))
		self.factor_level_matrix.fill_matrix(self.run_matrix, self.factor_list)
# 		print "Normal Run Sequence"
		#print_matrix(run_matrix)
		#m2 = random.sample(self.run_matrix, len(self.run_matrix))
		#print "Randomized Run Sequence"
		#print_matrix(m2)
	
	def get_run_matrix(self):
		return self.run_matrix
	
	def get_run_identifier(self):
		return self.factor_level_matrix.make_run_identifier(self.run_matrix[self.current_run_number])
	
	def get_run_count(self):
		return len(self.run_matrix)
	
	def set_run_number(self, run_number):
		'''
		This function sets the current run number (the row in the run matrix).
		'''
		self.current_run_number = run_number
		
	def get_current_factor_value_by_id(self, factor_id):
		'''
		Retrieves the currently active value for that factor in the currently
		active level
		'''
		found_index=-1
		for i,factor in enumerate(self.factor_list):
			if factor.id == factor_id:
				found_index=i
		
		if found_index==-1:
			return -1
		else:
			return self.factor_list[found_index].get_level(self.run_matrix[self.current_run_number][found_index])

	def get_current_factor_level_by_id(self, factor_id):
		'''
		Retrieves the currently active level for that factor
		'''
		found_index=-1
		for i,factor in enumerate(self.factor_list):
			if factor.id == factor_id:
				found_index=i
		
		if found_index==-1:
			return -1
		else:
			return self.run_matrix[self.current_run_number][found_index]

	def get_current_run_name(self):
		return self.factor_level_matrix.make_run_identifier(self.run_matrix[self.current_run_number])
	
	def get_actor_node_map(self):
		'''
		This function returns the abstract node to actor process mapping.
		Eiter it is a factor, then the current value is returned, or it is constant, 
		then that level is returned
		'''
		if self.actor_node_map_is_factor()==False:
			return self.node_processes.param_mapping.data
		else:
			id=self.get_actor_node_map_factor_id()
			map = self.get_current_factor_value_by_id(id)
			return map
		
	def get_all_spec_nodes(self):
		'''
		Returns all the nodes from the platform_spec tag
		'''
		result = []
		for node in self.platform_specs.actor_map:
			result.append(node)
		for node in self.platform_specs.env_map:
			result.append(node)	   
		return result
	
	def get_node_by_ip(self, ip):
		'''
		Returns the node dictionary for the node, identified by ip
		'''
		for node in self.platform_specs.actor_map:
			if node['real_ip']==ip:
				return node
		
if __name__ == '__main__':
	# Option parser
	parser = optparse.OptionParser(
		description='Parse XML experiment description',
		prog=os.path.basename(sys.argv[0]),
		version='%s 0.0.1' % os.path.basename(sys.argv[0]),
	)

	parser.add_option('-f', metavar='xmlfile', dest='xmlfile', help='file with description')
	
	options, arguments = parser.parse_args()
	
	if options.xmlfile:
		xmlfile = options.xmlfile
	else:
		print 'No xml file given.'
		exit()
	
	exp = experiment_description(xmlfile)
	exp.summary()

	
	

	
	
	print "\n======= Run Sequence (Parameter Variation)======\n"
	
	#build matrix
	n = 1
	for fact in exp.factor_list:
		n = n * fact.levels.get_len()
	#random.seed(0)
	print range(len(exp.factor_list[1].levels.level_list))
	print random.sample(range(len(exp.factor_list[1].levels.level_list)),exp.factor_list[1].levels.get_len())
	print "There must be %d runs" %n
	
