import sys
sys.path.append('/opt/local/Library/Frameworks/Python.framework/Versions/2.7/lib/python2.7')
sys.path.append('/opt/local/Library/Frameworks/Python.framework/Versions/2.7/lib/python2.7/site-packages')

import socket
import sqlite3
import struct
import pcapy
import datetime
import time
import os
import optparse
import glob
from exp_description import *
import matplotlib.pyplot as plt
import scipy as stats
import statsmodels.api as sm
#import numpy as np
import sys,getopt


def get_discovery_retries(startstep):
	retries=[startstep]
	while retries[-1] < dead/1000:
		retrystep = 2**len(retries)
		if retrystep < dead/1000:
			retries.append(retrystep)
		else:
			break
	return retries


def experiment_analyzer(sdratio):
	'''
	
	'''
	global conn
	global exp
	count = 0
	
	c = conn.cursor()
	x = []
	y=[]
	delay = []
	pkt_delay = []
	time_offset = []
	for n in range(4):
# 		print n
		delay.append([])
		pkt_delay.append([])
# 		print dead
		for i in range(exp.get_run_count()):
			#delay[n].append(30000)
			delay[n].append(dead)
			#pkt_delay[n].append(30000)
			pkt_delay[n].append(dead)

	#loop over run sequence
	fail = 0
	succeeded = 0
	timedout = 0
	valid_results = [0,0,0,0]
	
	num_responders = len(exp.get_responders())
	needed = min(num_responders, int(round(sdratio * num_responders) / 100 + 0.5))
	
	for run_number in range(exp.get_run_count()):
		###### SETUP LEVELS OF ALL FACTORS FOR THIS RUN ########
		exp.set_run_number(run_number)
		run_definition = exp.get_run_identifier()
		#print "exporting run number %d with combination %s" %(run_number,run_definition)
		#print "run_definition", run_definition
		c.execute("SELECT RunID FROM run_ids WHERE run_identifier=?",[run_definition])
		run_id = c.fetchone()[0]
		
		fact = exp.get_current_factor_level_by_id('fact_pairs')
		#print fact
		run_fact = exp.get_current_factor_level_by_id('fact_replication_id')
		all_nodes = exp.get_all_spec_nodes()
		for node in all_nodes:
			if node['real_id']== exp.get_requester()["real_id"]:

				#events=run_analyzer(run_id,node,c)
				#for deadline in range(30):
				#	resp[deadline] = resp[deadline] + get_responsiveness(run_id, node, deadline*1000)
				#delay[run_number] = get_delay(run_id, node)
				#res=check_packets(run_id, node, 30000)
				res = check_packets(run_id, node, dead)
				# checks for invalid runs and excludes the response times
				actornodes = [node]
				actornodes = actornodes + exp.get_responders()

				fails = check_routes(run_id, actornodes)
				
				#print res
				
				if res == -1 or fails > 0:
					fail = fail + 1
				else:
					index=valid_results[fact]
					delse = get_delay(run_id, node, needed)
					delay[fact][index] = delse
					x.append(delse)
					y.append(run_id)
					valid_results[fact] = valid_results[fact] + 1
					if delse < dead:
						succeeded = succeeded + 1
					else:
						timedout = timedout + 1
				break
		sys.stdout.write("\rAnalyzed Runs: %d, Valid: %d, Succeeded: %d, Timed out: %d, Failed: %d" % (run_number+1, valid_results[0], succeeded, timedout, fail))
		sys.stdout.flush()
	
	sys.stdout.write("\n")
	
	######## RESPONSIVENESS 1zu1 ############
	#for i in range(250):	
	#	print delay[3][i]
	symbols = ['k-','k--','k-.','k:']
	#for fact in range(4):
	fact=0
	res = []
	
	#z=stats.norm.cdf(x)
	#print z

	
	for i in range(30000):
		ok = 0
		
		#print pkt_delay
		for n in range(valid_results[fact]):
			
				if pkt_delay[fact][n]<i:
					ok = ok + 1
				#print ok
				res.append((ok*100/valid_results[fact])*0.01)
	
	ecdf = sm.distributions.ECDF(x)
			
	### Plotting starts here ###
	
	fn_split=fn.split("_")
# 	print "Client: %s" % fn_split[0]
# 	print "Provider: %s" % fn_split[1]
# 	print "%d VoIP Streams Load" % int(fn_split[3])
	if int(fn_split[3]) > 0:
		legend_string = "%d VoIP Streams Load" % int(fn_split[3])
	else:
		legend_string = "No Load"

	plt.figure(1)
	plt.plot(ecdf.x, ecdf.y, linestyle='-', drawstyle='steps', label=legend_string)

#Checks for validity of the routes from the ExtraRunMeasurements
def check_route(run_id, node):	

# 	c.execute("SELECT Content FROM ExtraRunMeasurements WHERE runID=? and nodeID=?", [run_id,node['real_id']] )
	c.execute("SELECT Content FROM ExtraRunMeasurements WHERE runID=? and nodeID=?", [run_id,node['real_id']] )
	routes = str(c.fetchone())
	if 'fail' in routes :
# 		print run_id,node['real_id']
# 		print " invalid run"
		#fail = fail+1
		return 1	
		
def check_routes(run_id, actornodes):

	actorsstring = ', '.join('?' * len(actornodes))
	query_string = "SELECT count(NodeID) FROM ExtraRunMeasurements WHERE runID=? and Content like 'fail%%' and nodeID in (%s)" % actorsstring

	query_args = [run_id]
	for actor in actornodes:
		query_args.append(actor['real_id'])

	c.execute(query_string, query_args)
	fails = c.fetchone()[0]
	
# 	if fails > 0:
# 		print "Run %d, Failed routes %s" % (run_id, fails)

	return fails
		
def check_packets(run_id, node, deadline_ms):
	'''
	Steps: First select packets of this run, "sent" and "received". "sent" is to be handled with care, as previously sent packets
	can be received again and have to be filtered out. This unfortunately can also be packets from other runs.
	When a packet from another run is detected as sent, it can be removed from the list, when a response arrives
	within the search window, then this search is false positive and must FAIL.
	'''
	# first get start/stop times
	c.execute("SELECT CommonTime FROM Events WHERE runID=? and nodeID=? and EventType='sd_start_search'", [run_id,node['real_id']] )
	#print "start_search"
	rows = c.fetchone()
	#print rows
	
	if rows==None:
		#print "Error, no search found in run ", run_id, node['real_id']
		return -1
	
	start_search_time = rows[0]
	start = db_timestamp_to_datetime(start_search_time)
	c.execute("SELECT CommonTime FROM Events WHERE runID=? and nodeID=? and EventType='sd_service_add'", [run_id,node['real_id']] )
	#print "sd_service_add"
	find_result = c.fetchone()
	#print find_result
	if find_result==None:
		#print "0"
		stop = start+datetime.timedelta(milliseconds=deadline_ms)
	else:
		stop = db_timestamp_to_datetime(find_result[0])
		if stop > start+datetime.timedelta(milliseconds=deadline_ms):
			stop = start+datetime.timedelta(milliseconds=deadline_ms)

	c.execute("SELECT * FROM Packets WHERE RunID=? and NodeID=? and SrcNodeID=? ORDER BY CommonTime ASC", [run_id, node['real_id'],node['real_id']])
	rows_send = c.fetchall()
	#print rows_send
	c.execute("SELECT * FROM Packets WHERE RunID=? and NodeID=? and SrcNodeID!=? ORDER BY CommonTime ASC", [run_id, node['real_id'],node['real_id']])
	rows_recv = c.fetchall()
	#print rows_recv
	# consider only packets within the search/timedout interval
	for sent in list(rows_send):
		sent_time = db_timestamp_to_datetime(sent[2])
		if sent_time < start or sent_time>stop:
			rows_send.remove(sent)
	pkt_analyzer = packet_analyzer()

	#print start
	#print stop
	# also, consider only responses
	for received in list(rows_recv):
		received_time = db_timestamp_to_datetime(received[2])
		pkt = received[4]
		ip=pkt_analyzer.decode_ip_packet(pkt)
		udp=pkt_analyzer.decode_udp_packet(ip['data'])
		mdns=pkt_analyzer.decode_mdns_packet(udp['data'])
		# mdns flag say, if response or not, must be response
		if received_time < start or received_time > stop or mdns['flags'] & 128!=128:
			#print "removing", received
			rows_recv.remove(received)

	# list packets by their transaction ID

	# remove duplicates and out of order packets from the sent
	sent_by_id = {}
	for i,sent in enumerate(list(rows_send)):	 
		pkt = sent[4]		
		id = socket.ntohs(struct.unpack('H',pkt[28:30])[0])
		if i==0: 
			last_id=id-1
			#print "Out of order %d %d" %( run_id, id), sent
		if id==last_id+1:
			last_id = id
			#print "correct oder", sent
			sent_by_id[id] = sent

	
	# find responses and BAD RESPONSES
	for received in rows_recv:
		pkt = received[4]
		id = socket.ntohs(struct.unpack('H',pkt[28:30])[0])
		#print "ResponseID: %d" %id
		found = 0
		for id_sent,sent in sent_by_id.items():
			if id==id_sent:
				#print "found same IDs", id
				found = 1
				t_requ = db_timestamp_to_datetime(sent[2])
				t_resp = db_timestamp_to_datetime(received[2])
				delay = t_resp - t_requ
				return delay.seconds*1000 + delay.microseconds / 1000
		if found==0:
			#print "Fail Runid=%s" %run_id, received
			return -1
				
	return deadline_ms

class packet_analyzer():
	
	def __init__(self):
		pass
	
	def get_dnssd_query_response_rtt(self):
		'''
		
		'''
		pass
	def decode_mdns_packet(self, p):
		d={}
		d['transaction_ID']=socket.ntohs(struct.unpack('H',p[0:2])[0])
		d['flags']=struct.unpack('H',p[2:4])[0]
		d['n_questions']=socket.ntohs(struct.unpack('H',p[4:6])[0])
		d['n_answerRRs']=socket.ntohs(struct.unpack('H',p[6:8])[0])
		d['n_authRRs']=socket.ntohs(struct.unpack('H',p[8:10])[0])
		d['n_addRRs']=socket.ntohs(struct.unpack('H',p[10:12])[0])
		return d

	def decode_udp_packet(self, p):
		d={}
		d['src_port']=socket.ntohs(struct.unpack('H',p[0:2])[0])
		d['dst_port']=socket.ntohs(struct.unpack('H',p[2:4])[0])
		d['length']=socket.ntohs(struct.unpack('H',p[4:6])[0])
		d['checksum']=socket.ntohs(struct.unpack('H',p[6:8])[0])
		d['data']=p[8:]
		return d

	def decode_ip_packet(self, s):
		d={}
		d['version']=(ord(s[0]) & 0xf0) >> 4
		d['header_len']=ord(s[0]) & 0x0f
		d['tos']=ord(s[1])
		d['total_len']=socket.ntohs(struct.unpack('H',s[2:4])[0])
		d['id']=socket.ntohs(struct.unpack('H',s[4:6])[0])
		d['flags']=(ord(s[6]) & 0xe0) >> 5
		d['fragment_offset']=socket.ntohs(struct.unpack('H',s[6:8])[0] & 0x1f)
		d['ttl']=ord(s[8])
		d['protocol']=ord(s[9])
		d['checksum']=socket.ntohs(struct.unpack('H',s[10:12])[0])
		d['source_address']=struct.unpack('i',s[12:16])[0]
		d['destination_address']=struct.unpack('i',s[16:20])[0]
		if d['header_len']>5:
			d['options']=s[20:4*(d['header_len']-5)]
		else:
			d['options']=None
		d['data']=s[4*d['header_len']:]
		return d
	
	def decode_eth_packet(self, p):
		d={}
		d['dst_mac']=0#struct.unpack('H',p[0:6])[0]
		d['src_mac']=0#struct.unpack('H',p[6:12])[0]
		d['type']=socket.ntohs(struct.unpack('H',p[12:14])[0])
		d['data']=p[14:]
		return d

	def packet_tracker(self, hdr, data):
		'''
		scans packets for pairs with same queryID and for the first return rtt
		'''
		global query
		global avg
		global count
		global max
		global min
		
		curr_hdr={}
		curr_hdr['ts_s'],curr_hdr['ts_us'] = hdr.getts()
		curr_hdr['len']=hdr.getlen()
		
		ts = datetime.datetime.fromtimestamp(curr_hdr['ts_s'])
		ts = ts + datetime.timedelta(microseconds=curr_hdr['ts_us'])
		d3 = None
		#d = self.decode_eth_packet(data)
		#print d
		#if d['type']==2048: #IP
		d = self.decode_ip_packet(data)
		if d['protocol']==17: # UDP
			d2 = self.decode_udp_packet(d['data'])
			if d2['dst_port']==5353:
				d3 = self.decode_mdns_packet(d2['data'])
		
		if d3==None:
			print "not a mdns packet", d3
			return
		
		# if this is a query, save the id and time
		if d3['flags']==0: #Query
			self.queries.append({'id':d3['transaction_ID'], 'ts':ts})
		else: #response
			#if query[d3['transaction_ID']]==None:
			#	print "Invalid response, ignoring this packet"
			#	return
			self.responses.append({'id':d3['transaction_ID'], 'ts':ts})
							
			
	def load_packet_into_list(self, filename):
		self.responses = []
		self.queries = []
		#print ("Parsing file %s" % (filename))	
		p = pcapy.open_offline(filename)
		p.loop(0, self.packet_tracker)
		#print self.queries
		#print ""
		#print self.responses
	
	def find_first_rtt_between(self, start_ts, end_ts):
		match = 0
		for (id,query) in enumerate(self.queries):
			if query['ts']>start_ts and query['ts']<end_ts:
				#print query	 
				for (id2,response) in enumerate(self.responses):
					if response['ts']>start_ts and response['ts']<end_ts:
						if response['id']==query['id']:
							diff = response['ts']-query['ts']
							#print "Found match, diff ",diff
							match = match + 1
		print match

counter = 0
events_merge_file_name = "merged_events.csv"
event_log_file_name	= "event_log_"

def _get_subdirs(dir):
	return [name for name in os.listdir(dir)
			if os.path.isdir(os.path.join(dir,name))]

def _get_files(dir, mask):
	return
	
def runcapture_dir_analyzer(dir):
	if dir=="capture":
		return

def parse_line(line, run, owner):
	'''
	Each line consists of a timestamp,type,param
	The timestamp is concerted into epoch value
	'''
	list = line.split(',')

	dt, _, us= list[0].partition(".")
	dt= datetime.datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
	us= int(us.rstrip("Z"), 10)
	ret = dt + datetime.timedelta(microseconds=us)+datetime.timedelta(milliseconds=run.timediff_ms)
	return {'ts':ret, 'type':list[1], 'param':list[2], 'origin':owner}
	#gt("2008-08-12T12:20:30.656234Z")
	#datetime.datetime(2008, 8, 12, 12, 20, 30, 656234)	
		 
def db_timestamp_to_datetime(db_timestamp):
	dt, _, us= db_timestamp.partition(".")
	dt= datetime.datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
	us= int(us.rstrip("Z"), 10)
	return dt + datetime.timedelta(microseconds=us)

def get_delay(run_id, node, needed):
	''' gets the search --> add delay from the event list
	'''
	y=[]
	c.execute("SELECT CommonTime FROM Events WHERE runID=? and nodeID=? and EventType='sd_start_search'", [run_id,node['real_id']] )
	start_search_time = c.fetchone()[0]
	c.execute("SELECT CommonTime FROM Events WHERE runID=? and nodeID=? and EventType='sd_service_add'", [run_id,node['real_id']] )
	find_result = c.fetchall()

	if find_result==None:
		return dead
	elif len(find_result) < needed:
		return dead
	else:
		stop_search_time = find_result[needed-1][0]
		start = db_timestamp_to_datetime(start_search_time)
		stop = db_timestamp_to_datetime(stop_search_time)
		delay = stop-start
		#print delay.seconds*1000 + delay.microseconds / 1000
		delsec = delay.seconds*1000 + delay.microseconds / 1000
		#print "response"
		#print delsec
	
		#print "run id"
		#print run_id
		#plt.xlabel('Deadline in ms',{'fontsize':'x-large'})
		#plt.ylabel('Responsiveness',{'fontsize':'x-large'})
		return delsec

def print_plot():
	plt.xlabel('Deadline in ms',{'fontsize':'x-large'})
	plt.ylabel('Responsiveness',{'fontsize':'x-large'})
	#plt.legend(('no load', '26 VoIP', '53 VoIP', '80 VoIP'),
	#	'right', shadow=True)
	plt.grid(True)
	plt.legend(loc = "lower right")
	plt.xlim([0,dead])
	plt.hold(True)
	
# 	plt.set_xticklabels(plt.get_xticks()/1000)

# 	savename = fn + "_" + str(sdratio) + ".pdf"
	savename = "plot.pdf"
	plt.savefig(savename, dpi=600)

	
if __name__ == '__main__':
	global conn
	global cfg_search_fail_value
	global csv_file
	global dead
	global fn
	
	cfg_search_fail_value = -1000
	# Option parser
	parser = optparse.OptionParser(
		description='Analyzer for done Service Discovery Experiments.',
		prog=os.path.basename(sys.argv[0]),
		version='%s 0.0.1' % os.path.basename(sys.argv[0]),
	)
	
# 	multi = False
	csv_file = "/tmp/results.csv"
	parser.add_option('-d', '--database', action='append', default = [], dest='database', help='the database file')
	
	parser.add_option('-l', metavar='deadline', type='int', dest='deadline', help='the deadline')
	parser.add_option('-x', metavar='exp_file', dest='exp_file', help='the abstract experiment description')
	parser.add_option('-o', metavar='csv_file', dest='csv_file', help='the file to which the results are written')
# 	parser.add_option('-m', action='store_true', dest='multi', help='analyze a multiple instances experiment')
	parser.add_option('-r' ,metavar='ratio', type='int', dest='sdratio', help='percentage of service instances needed to be found', default = 100)
	
	options, arguments = parser.parse_args()

		
	if options.csv_file!=None:
		csv_file = options.csv_file

	if options.database == []:
		print "Database file is needed"
		exit()
# 	else:
# 		for db in options.database:
# 			print db
# 		exit()
	
	if options.deadline == None:
		print "Deadline is needed"
		exit()
	else:
		dead = options.deadline
# 		print "dead",dead
	
	
	#print "Manu"
	
	for database in options.database:
	
		fn = str(database.split('.')[0].split('/')[-1])
		print "Database %s" % fn

		conn = sqlite3.connect(database)
		c = conn.cursor()
		c.execute("SELECT expXML FROM ExperimentInfo")
		row=c.fetchone()
		if row==None:
			print "no XML description in database file"
		fd = open('/tmp/exp_xml','w')
		fd.write(row[0])
		fd.close()
		
		if options.exp_file != None:
			exp = experiment_description(options.exp_file)
		else:
			exp = experiment_description('/tmp/exp_xml')
#		print exp.platform_specs.actor_map
		#print exp.get_requester()
	
		experiment_analyzer(options.sdratio)

	print_plot()