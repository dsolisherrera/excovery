import sys
#sys.path.append('/opt/local/Library/Frameworks/Python.framework/Versions/2.7/lib/python2.7')
#sys.path.append('/opt/local/Library/Frameworks/Python.framework/Versions/2.7/lib/python2.7/site-packages')

import struct
import zlib
from exp_description import *
import pcapy
import datetime
import sqlite3
import json
import zlib

def init_db():
	global conn 
	c = conn.cursor()

	c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=''")
	if c.fetchone()==None:
		# Create table
		c.execute('''CREATE TABLE "run_ids" (
				"runID" INTEGER PRIMARY KEY AUTOINCREMENT,
				"run_identifier" TEXT
			)		 '''	 )

	c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='EEFiles'")
	if c.fetchone()==None:
		# Create table
		c.execute('''CREATE TABLE "EEFiles" (
			"ID" INTEGER PRIMARY KEY AUTOINCREMENT,
			"File" BLOB)'''
		)
	
	c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Events'")
	if c.fetchone()==None:
		c.execute('''
					CREATE TABLE "Events" (
				"RunID" INTEGER,
				"NodeID" INTEGER,
				"CommonTime" TEXT,
				"EventType" TEXT,
				"Parameter" TEXT
			) ''')
		
	c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ExperimentInfo'")
	if c.fetchone()==None:
		c.execute('''
			CREATE TABLE "ExperimentInfo" (
				"ExpXML" TEXT,
				"EEVersion" TEXT,
				"Name" TEXT,
				"Comment" TEXT
			)''')

	c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='NodesIP'")
	if c.fetchone()==None:
		c.execute('''CREATE TABLE "NodesIP" (
				"NodeID" TEXT,
				"IP_Address" TEXT
			)''')
	
	c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ExperimentMeasurements'")
	if c.fetchone()==None:
		c.execute('''CREATE TABLE "ExperimentMeasurements" (
				"ID" INTEGER PRIMARY KEY,
				"NodeID" TEXT,
				"Name" TEXT,
				"Content" TEXT
			)''')

	c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ExtraRunMeasurements'")
	if c.fetchone()==None:
		c.execute('''CREATE TABLE "ExtraRunMeasurements" (
			"RunID" INTEGER,
			"NodeID" INTEGER,
			"Name" TEXT,
			"Content" TEXT
			)
		''')

	c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Links'")
	if c.fetchone()==None:
		c.execute('''
				CREATE TABLE "Links" (
				"RunID" INTEGER,
				"NodeIP" TEXT,
                "NeighborIP" TEXT,
				"LQ" REAL,
				"NLQ" REAL
			) ''')
			
	c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='OLSR'")
	if c.fetchone()==None:
		c.execute('''
				CREATE TABLE "OLSR" (
				"RunID" INTEGER,
				"NodeID" TEXT,
                "OLSR" BLOB
			) ''')	
	
	c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Logs'")
	if c.fetchone()==None:
		c.execute('''CREATE TABLE "Logs" (
				"NodeID" TEXT,
				"Log" BLOB
			)''')
	
	c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='PacketsBmf0'")
	if c.fetchone()==None:
		c.execute('''CREATE TABLE "PacketsBmf0" (
			"RunID" INTEGER,
			"NodeID" INTEGER,
			"CommonTime" TEXT,
			"SrcNodeID" TEXT,
			"Data" BLOB
			)''')

	c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='PacketsWLAN2'")
	if c.fetchone()==None:
		c.execute('''CREATE TABLE "PacketsWLAN2" (
			"RunID" INTEGER,
			"NodeID" INTEGER,
			"CommonTime" TEXT,
			"SrcNodeID" TEXT,
			"Data" BLOB
			)''')
	
	c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='RunInfos'")
	if c.fetchone()==None:
		c.execute('''	   CREATE TABLE "RunInfos" (
			"RunID" INTEGER,
			"NodeID" INTEGER,
			"StartTime" TEXT,
			"TimeDiff" TEXT
			)''')
		
#	c.execute('''CREATE INDEX "id" on measurements (runID ASC)''')
		
	# Save (commit) the changes
	conn.commit()
	# We can also close the cursor if we are done with it
	c.close()

class exp_event_list:
	def __init__(self):
	   self.event_list = [] 
	
	def load_from_file(self, file):
		self.event_list = []
		fd = open(file)
		i = 0
		event_list = []
		for line in fd:
			if i == 0 or line.split(',')[0] == "timestamp":
				i = i +1
				continue #skip the description line
			try:			
				self.event_list.append(self.parse_line(line))
			except:
				print "Error in file ", file
				raise()
			#event_list.append("%s,%s" %(line,node_name))
		fd.close()

		return self.event_list
		
	def parse_line(self, line):
		'''
		Each line consists of a timestamp,type,param
		The timestamp is concerted into epoch value
		'''
		list = line.split(',')

		dt, _, us = list[0].partition(".")
		if _ != ".":
			_, us = [".", "000000"]
			list[0] = list[0] + ".000000"

		dt= datetime.datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
		us= int(us.rstrip("Z"), 10)
		ret = dt + datetime.timedelta(microseconds=us)
		## patch old event types:
		if list[1]=="SD_init": list[1]="sd_init_done"
		if list[1]=="SD_exit": list[1]="sd_exit"
		if list[1]=="SD_start_search": list[1]="sd_start_search"
		if list[1]=="SD_stop_search": list[1]="sd_stop_search"
		if list[1]=="SD_publish": list[1]="sd_start_publish"
		if list[1]=="SD_add": list[1]="sd_service_add"
		return {'ts':ret, 'ts_string':list[0],'EventType':list[1], 'Parameter':list[2] }
		#gt("2008-08-12T12:20:30.656234Z")
		#datetime.datetime(2008, 8, 12, 12, 20, 30, 656234)


def get_packet_list(file, timediff,pos):
    '''
    returns an dict {'ts' commonTime, 'srcNode', 'data'}
    '''
    global exp
    diff = datetime.timedelta(milliseconds=timediff)
    p = pcapy.open_offline(file)
    done = False
    packet_list = []
    while done==False:
        try:
            (hdr,data) = p.next()
            curr_hdr = {}
            curr_hdr['ts_s'],curr_hdr['ts_us'] = hdr.getts()
            ts = datetime.datetime.fromtimestamp(curr_hdr['ts_s'])
            ts = ts + datetime.timedelta(microseconds=curr_hdr['ts_us'])
            ts = ts + diff
            
            #ipaddr=struct.unpack('B',data[12:16])[0]
            if pos == "bmp":
                ip0=struct.unpack('B',data[12])[0]
                ip1=struct.unpack('B',data[13])[0]
                ip2=struct.unpack('B',data[14])[0]
                ip3=struct.unpack('B',data[15])[0]
            else:
                ip0=struct.unpack('B',data[26])[0]
                ip1=struct.unpack('B',data[27])[0]
                ip2=struct.unpack('B',data[28])[0]
                ip3=struct.unpack('B',data[29])[0]
            
            ip = "%d.%d.%d.%d" % (ip0,ip1,ip2,ip3)
            #node ID
            node=exp.get_node_by_ip(ip)
            
            try:
                packet_list.append({'CommonTime':ts, 'SrcNodeID':node['real_id'], 'Data':data})
            except TypeError:
                print ">>> OOOOOPS!"
                print ">>> Does one of you nodes have the wrong IP in the XML file?"
                print ">>> Aborting ..."
                continue
                
            #print "Packet TS:",ts

        except pcapy.PcapError:
            done=True
    return packet_list


def get_links_measurements(exp_dir, run_id, db_run_id , node, c,fmt='json'):
	if fmt == 'txt':
		start = 0
		fd = open("%s/nodes/%s/links/%s.log" % (exp_dir,run_id, node['real_id']))
		i = 0
		for line in fd:
			links = line.split()
			if len(links) == 0 and start == 1:
				break
			for i in range(len(links)):
				if links[i] == 'INFINITE':
					links[i] = "infinity"
			if start == 1:
				c.execute("INSERT INTO Links (RunID, NodeIP, NeighborIP, LQ, NLQ) VALUES (?,?,?,?,?)",  [db_run_id, links[0],links[1],links[3],links[4]])
	   
			if "Local" in links:
				start = 1 
		# Need to find a proper way to save the text file
		#c.execute("INSERT INTO OLSR (RunID,NodeID, OLSR) VALUES (?,?,?)",[db_run_id,node['real_id'], sqlite3.Binary(zlib.compress(fd.read()))])
		fd.close()
	else:
		fd = open("%s/nodes/%s/links/%s.json" % (exp_dir,run_id, node['real_id']))
		olsr = json.load(fd)
		for link in olsr['links']:
			c.execute("INSERT INTO Links (RunID, NodeIP, NeighborIP, LQ, NLQ) VALUES (?,?,?,?,?)",  [db_run_id, link['localIP'],link['remoteIP'],link['linkQuality'],link['neighborLinkQuality']])
			
		c.execute("INSERT INTO OLSR (RunID,NodeID, OLSR) VALUES (?,?,?)",[db_run_id,node['real_id'], sqlite3.Binary(zlib.compress(json.dumps(olsr)))])
		fd.close()
	
		
def get_extra_run_measurements(exp_dir, run_id, node):
	'''
	
	'''
	fd = open("%s/nodes/%s/routes/%s.log" % (exp_dir,run_id, node['real_id']))
	i = 0
	for line in fd:		
		routes = line
	fd.close()
	return routes

def get_log_file(exp_dir, node):
	fd = open("%s/nodes/RPC-Server_%s.log" % (exp_dir, node['real_id']))
	i = 0
	log = fd.read()
	log = zlib.compress(log)
	fd.close()
	return log

def run_dir_importer(exp_dir, run_identifier, db_run_id, node, c,olsr_fmt):
	'''
	
	'''
	#get events
	event_list = exp_event_list()
	event_list.load_from_file("%s/nodes/%s/event_log_%s.log" % (exp_dir, run_identifier, node['real_id']))
	
	time_diff = 0
	#get time diff info
	if node['abstract_id']!="":  
		fd = open("%s/master/%s/ping_t_%s" % (exp_dir,run_identifier, node['real_id']))
		i = 0
		offset_1 = 0
		for line in fd:		
			if i == 3:
				#fetch first offset
				try:
					offset_1 = int(line)
				except ValueError:
					last_run_identifier = run_identifier.split('_')
					last_run_identifier[-1] = str(int(last_run_identifier[-1])-1)
					last_run_identifier = '_'.join(last_run_identifier)
					fd_last = open("%s/master/%s/ping_t_%s" % (exp_dir,last_run_identifier, node['real_id']))
					i_last = 0
					for line_last in fd_last:		
						if i_last == 3:
							#fetch first offset
							offset_1 = int(line_last)
						if i_last == 5:
							offset_2 = int(line_last)
							break
						i_last = i_last +1 
					fd_last.close()
					break
			if i == 5:
				offset_2 = int(line)
				break
			i = i +1 
		fd.close()
		# todo check calculation
		time_diff = offset_1 #+ abs(offset_2))/2
	
	#print "Time_diff=",time_diff
	try:
		c.execute("INSERT INTO RunInfos (RunID, NodeID, StartTime, TimeDiff) VALUES(?,?,?,?)",[db_run_id,node['real_id'],event_list.event_list[0]['ts_string'],time_diff])
	except IndexError:
		sys.stdout.flush()
		sys.stdout.write("\n")
		print ">>> OOOOOPS!"
		print ">>> We have an index error."
		print "db_run_id: %d" % db_run_id
		print "node: %s" % node
		print "node['real_id']: %s" % node['real_id']
		print "event_list: %s" % event_list
		print "event_list.event_list: %s" % event_list.event_list
		print "event_list.event_list[0]: %s" % event_list.event_list[0]
		print "event_list.event_list[0]['ts_string']: %s" % event_list.event_list[0]['ts_string']
		print "time_diff: %d" % time_diff
		raise()
	
	for event in event_list.event_list:
		diff = datetime.timedelta(milliseconds=time_diff)
		commonTime = event['ts'] + diff
		c.execute("INSERT INTO Events (RunID, NodeID, CommonTime, EventType, Parameter) VALUES (?,?,?,?,?)", [db_run_id,node['real_id'],commonTime, event['EventType'],event['Parameter']])
	
	# parse packets
	if node['abstract_id']!="": 
		cap = "%s/nodes/%s/capture/%s_bmf0.pcap" %(exp_dir, run_identifier,node['real_id'])
		packet_list = get_packet_list(cap, time_diff,"bmp")
		#print len(packet_list)
		#print packet_list
		for packet in packet_list:
			c.execute("INSERT INTO PacketsBmf0 (RunID,NodeID,CommonTime, SrcNodeId, Data) VALUES (?,?,?,?,?)", [db_run_id,node['real_id'],packet['CommonTime'],packet['SrcNodeID'],sqlite3.Binary(packet['Data'])])	 

	if node['abstract_id']!="": 
		cap = "%s/nodes/%s/capture/%s_wlan2.pcap" %(exp_dir, run_identifier,node['real_id'])
		packet_list = get_packet_list(cap, time_diff,"wlan2")
		#print len(packet_list)
		#print packet_list
		for packet in packet_list:
			c.execute("INSERT INTO PacketsWLAN2 (RunID,NodeID,CommonTime, SrcNodeId, Data) VALUES (?,?,?,?,?)", [db_run_id,node['real_id'],packet['CommonTime'],packet['SrcNodeID'],sqlite3.Binary(packet['Data'])])	
   
	# ExtraRun measurements
	routes = get_extra_run_measurements(exp_dir,run_identifier, node)
	c.execute("INSERT INTO ExtraRunMeasurements (RunID, NodeID, Name, Content) VALUES (?,?,?,?)", [db_run_id, node['real_id'],"routes",routes])

    # Topology/links measurements given by OLSR
	get_links_measurements(exp_dir, run_identifier, db_run_id , node, c, fmt=olsr_fmt)

def get_topo(exp_dir, node, node2):
	fd = open("%s/nodes/topology/traceroute_%s_%s" % (exp_dir, node['real_id'],node2['real_id']))
	i = 0
	s = fd.read()
	#s = zlib.compress(s)
	fd.close()
	return s
	
def experiment_dir_importer(exp_dir,olsr_fmt):
	global csv_file
	global exp
	global conn
	
	c = conn.cursor()
	#loop over run sequence
	for run_number in range(exp.get_run_count()):
		###### SETUP LEVELS OF ALL FACTORS FOR THIS RUN ########
		exp.set_run_number(run_number)
		run_definition = exp.get_run_identifier()
		sys.stdout.write("\rImporting run ID %d" % run_number)
		sys.stdout.flush()
		c.execute("INSERT INTO run_ids (run_identifier) VALUES (?)", [run_definition])
		run_id = c.lastrowid
		# import measurements from nodes and master
		# event lists, packets, topo, timediff
		all_nodes = exp.get_all_spec_nodes()
		for node in all_nodes:
			#if node['real_id']=="t9-007":
			run_dir_importer(exp_dir, run_definition, run_id, node, c,olsr_fmt)

	sys.stdout.write("\r%d runs imported                  " % (run_number + 1))
	sys.stdout.flush()
	sys.stdout.write("\n")
	conn.commit()		
	 # get log files
	nodenum = 0
	for node in all_nodes:
		nodenum = nodenum + 1
		c.execute("INSERT INTO NodesIP (NodeID, IP_Address) VALUES (?,?)",[node['real_id'], node['real_ip']])
		try:
			sys.stdout.write("\rInserting log for node %d" % nodenum)
			sys.stdout.flush()
			log = get_log_file(exp_dir, node)
			c.execute("INSERT INTO Logs (NodeID, Log) VALUES (?,?)",[node['real_id'], sqlite3.Binary(log)])
		except:
			sys.stdout.write(" ... no logfile")
	sys.stdout.write("\rLogs for %d nodes inserted                  " % nodenum)
	sys.stdout.flush()
	sys.stdout.write("\n")
	
	# get program files
	conn.commit()
	# get experiment measurements
	for node in all_nodes:
		for node2 in all_nodes:
			if node!= node2:
				if node['abstract_id']!="" and node2['abstract_id']!="":
					topo = get_topo(exp_dir, node, node2) 
					c.execute("INSERT INTO ExperimentMeasurements (NodeID, Name, Content) VALUES (?,'hopcount',?)",[node['real_id'],topo])
	
	# get experiment description
	
	conn.commit()
	
if __name__ == '__main__':
	global exp
	global conn
	
	
	
	parser = optparse.OptionParser(
		description='Import Service Discovery Experiments.',
		prog=os.path.basename(sys.argv[0]),
		version='%s 0.0.1' % os.path.basename(sys.argv[0]),
	)
	parser.add_option('-e', metavar='experiment_dir', dest='experiment_dir', help='Name of the experiment')
	parser.add_option('-x', metavar='exp_file', dest='exp_file', help='the abstract experiment description')
	parser.add_option('-o', metavar='csv_file', dest='csv_file', help='the file to which the results are written')
	parser.add_option('-d', metavar='database', dest='database', help='the file that should contain the database')
	parser.add_option('--olsr', metavar='olsr_fmt', dest='olsr_fmt', help='the format in which the olsr data was generated')
	options, arguments = parser.parse_args()
	
	if options.experiment_dir==None:
		print "Need experiment dir"
		exit()
	if options.csv_file!=None:
		csv_file = options.csv_file
	
	if options.database==None:
		conn = sqlite3.connect('/tmp/example4')
	else:
		conn = sqlite3.connect(options.database)
		
	if options.olsr_fmt!=None:
		olsr_fmt = options.olsr_fmt
	else:
		olsr_fmt = 'json'
		
	exp = experiment_description(options.exp_file)
	#exp.summary()
	init_db()
	experiment_dir_importer(options.experiment_dir,olsr_fmt)
	c = conn.cursor()
	fd = open(options.exp_file)
	xml = fd.read()
	fd.close()
	c.execute("INSERT INTO ExperimentInfo (ExpXML,EEVersion,Name,Comment) VALUES (?,'0.4',?,?)",[xml, exp.experiment_name,""])
	conn.commit()
	print "Creating indexes"
	c.execute('''CREATE INDEX "events_index" on events (RunID ASC, NodeID ASC)''')
	c.execute('''CREATE INDEX "packet_index" on packets (RunID ASC, NodeID ASC, SrcNodeID ASC)''')
	c.execute('''CREATE INDEX "runinfo_index" on runinfos (RunID ASC, NodeID ASC)''')
	conn.commit()
