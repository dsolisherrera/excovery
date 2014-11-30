'''
This is the main analyze script
'''
import socket
import sqlite3
import struct
import pcapy
import datetime
import time
import os
import argparse
import glob
from exp_description import *
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import scipy as stats
import statsmodels.api as sm
from array import array
import sys,getopt
import numpy as np

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
            #    print "Invalid response, ignoring this packet"
            #    return
            self.responses.append({'id':d3['transaction_ID'], 'ts':ts})
                            
    def load_packet_into_list(self, filename):
        self.responses = []
        self.queries   = []
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

class run_info:
    timediff_ms=0
    def __init__(self):
        self.timediff_ms = 0
        self.start_time  = 0

class ScaledLocator(mpl.ticker.MaxNLocator):
    """
    Locates regular intervals along an axis scaled by *dx* and shifted by
    *x0*. For example, this would locate minutes on an axis plotted in seconds
    if dx=60.  This differs from MultipleLocator in that an approriate interval
    of dx units will be chosen similar to the default MaxNLocator.
    """
    def __init__(self, dx=1.0, x0=0.0):
        self.dx = dx
        self.x0 = x0
        mpl.ticker.MaxNLocator.__init__(self, nbins=9, steps=[1, 2, 5, 10])

    def rescale(self, x):
        return x / self.dx + self.x0
    def inv_rescale(self, x):
        return  (x - self.x0) * self.dx

    def __call__(self): 
        vmin, vmax = self.axis.get_view_interval()
        vmin, vmax = self.rescale(vmin), self.rescale(vmax)
        vmin, vmax = mpl.transforms.nonsingular(vmin, vmax, expander = 0.05)
        locs = self.bin_boundaries(vmin, vmax)
        locs = self.inv_rescale(locs)
        prune = self._prune
        if prune=='lower':
            locs = locs[1:]
        elif prune=='upper':
            locs = locs[:-1]
        elif prune=='both':
            locs = locs[1:-1]
        return self.raise_if_exceeds(locs)

class ScaledFormatter(mpl.ticker.OldScalarFormatter):
    """Formats tick labels scaled by *dx* and shifted by *x0*."""
    def __init__(self, dx=1.0, x0=0.0, **kwargs):
        self.dx, self.x0 = dx, x0

    def rescale(self, x):
        return x / self.dx + self.x0

    def __call__(self, x, pos=None):
        xmin, xmax = self.axis.get_view_interval()
        xmin, xmax = self.rescale(xmin), self.rescale(xmax)
        d = abs(xmax - xmin)
        x = self.rescale(x)
        s = self.pprint_val(x, d)
        return s

counter = 0
events_merge_file_name = "merged_events.csv"
event_log_file_name    = "event_log_"

def db_timestamp_to_datetime(db_timestamp):
    dt, _, us= db_timestamp.partition(".")
    dt= datetime.datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
    us= int(us.rstrip("Z"), 10)
    return  dt + datetime.timedelta(microseconds=us)

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
  
def is_actor_logfile(logfilename):
    '''
    returns true if the node is an actor
    '''
    global specs
    for n in specs.node_mapping:
        if logfilename.find("event_log_%s.log" % n['real_id'])!=-1:
            return True
    return False
    
def get_search_time_ms(event_list):
    global cfg_search_fail_value
    start_time=None
    find_time=None
    for event in event_list:
        if(event['type']=="SD_start_search"):
            start_time = event['ts']
        if(event['type']=="SD_add"):
            find_time = event['ts']
    
    if start_time!=None and find_time!=None:
        delta=find_time-start_time
        ms = delta.microseconds+delta.seconds*100000
        ms = ms / 1000
        return ms
    else:
        return cfg_search_fail_value
   
def get_search_time_ms_multi(event_list):
    '''
    returns a dict, with find names as index and for each find the delay
    '''
    global specs
    global cfg_search_fail_value
    start_time=None
    find_time=None
    results = {}
    for i in specs.node_mapping:
        results[i['real_id']]= cfg_search_fail_value
    
    for event in event_list:
        if(event['type']=="SD_start_search"):
            start_time = event['ts']
        if(event['type']=="SD_add"):
            find_time = event['ts']
            if start_time!=None and find_time!=None:
                delta=find_time-start_time
                ms = delta.microseconds+delta.seconds*100000
                ms = ms / 1000
                results[event['param']]=ms
    return results

def get_search_find_number(event_list,deadline_ms):
    '''
    retrieves the number of found services before
    the deadline given was reached
    Parameters:
        event_list: List of events to search
        deadline_ms: deadline for the services search 
    '''
    num_of_finds = 0
    count_finds_now = 0
    for event in event_list:
        if event['type']=="SD_start_search":
            start_time=event['ts']
            count_finds_now = 1
        if count_finds_now == 1 and event['type']=="SD_add" and event['ts']<start_time+datetime.timedelta(milliseconds=deadline_ms):
            num_of_finds = num_of_finds +1
        if event['type']=="SD_stop_search":
            return num_of_finds

def get_index_of_event(event_list, event_type):
    '''
    gets the index of the first occurence of an event in the event list
    '''
    for (i,e) in enumerate(event_list):
        if e['type']==event_type:
            return i
    

def get_time_offset(node, run):
    '''
    This function retrieves the estimated time offset for a node in a run
    '''
    fd = open("%s/%s/%s" % (path, current_dir,item))
    i = 0
    for line in fd:
        if i == 0:
            i = i +1
            continue #skip the description line
        line = line.replace('\n','')
        event=parse_line(line,run_info,node_name)
        event_list.append(event)
        #event_list.append("%s,%s" %(line,node_name))
    fd.close()
    
def get_discovery_retries(startstep):
    retries=[startstep]
    while retries[-1] < deadline/1000:
        retrystep = 2**len(retries)
        if retrystep < deadline/1000:
            retries.append(retrystep)
        else:
            break
    return retries    

def _get_subdirs(dir):
    return [name for name in os.listdir(dir)
            if  os.path.isdir(os.path.join(dir,name))]

def _get_files(dir, mask):
    return
    
def runcapture_dir_analyzer(dir):
    if dir=="capture":
        return

def run_dir_analyzer(path, current_dir):
    global event_log_file_name
    global events_merge_file
    global specs
    #print "Analyzing run: %s" % current_dir
    #print "Creating Summary of distributed events into one event file %s" % events_merge_file_name
    event_log_file_name = ".log"
    
    pkt = packet_analyzer()
    pkt.load_packet_into_list("%s/%s/capture/t9-007.pcap" % (path,current_dir))
    
    event_list = []
    ri = run_info()
    for item in os.listdir("%s/%s" % (path,current_dir)):
        if is_actor_logfile(item):
            #print "Reading event log file %s" %item
            l=item.find(event_log_file_name)
            l=l+len(event_log_file_name)
            r=item.find(".log")
            node_name = item[l:r]
            #print "node name found is %s" % node_name
            fd = open("%s/%s/%s" % (path, current_dir,item))
            i = 0
            for line in fd:
                if i == 0:
                    i = i +1
                    continue #skip the description line
                line = line.replace('\n','')
                event=parse_line(line,run_info,node_name)
                event_list.append(event)
                #event_list.append("%s,%s" %(line,node_name))
            fd.close()
   
    sor=sorted(event_list, key=lambda event: event['ts'])
    i = get_index_of_event(event_list, "SD_start_search")

    start_search = event_list[i]
    #print "Time of start search: ",start_search
    #pkt.find_first_rtt_between(start_search['ts'], start_search['ts']+datetime.timedelta(seconds=30))
    #find fails
    
    #r=get_search_find_number(sor,200)

    #filter
    diff= get_search_time_ms(event_list)
    
    return diff    
    
def run_dir_analyzer_multi(path, current_dir):
    global event_log_file_name
    global events_merge_file
    global specs
    #print "Analyzing run: %s" % current_dir
    #print "Creating Summary of distributed events into one event file %s" % events_merge_file_name
    event_log_file_name = ".log"
    
    pkt = packet_analyzer()
    pkt.load_packet_into_list("%s/%s/capture/t9-007.pcap" % (path,current_dir))
    
    event_list = []
    ri = run_info()
    for item in os.listdir("%s/%s" % (path,current_dir)):
        if is_actor_logfile(item):
            #print "Reading event log file %s" %item
            l=item.find(event_log_file_name)
            l=l+len(event_log_file_name)
            r=item.find(".log")
            node_name = item[l:r]
            #print "node name found is %s" % node_name
            fd = open("%s/%s/%s" % (path, current_dir,item))
            i = 0
            for line in fd:
                if i == 0:
                    i = i +1
                    continue #skip the description line
                line = line.replace('\n','')
                event=parse_line(line,run_info,node_name)
                event_list.append(event)
                #event_list.append("%s,%s" %(line,node_name))
            fd.close()
   
    sor=sorted(event_list, key=lambda event: event['ts'])
    i = get_index_of_event(event_list, "SD_start_search")

    start_search = event_list[i]
    #print "Time of start search: ",start_search
    #pkt.find_first_rtt_between(start_search['ts'], start_search['ts']+datetime.timedelta(seconds=30))
    #find fails
    
    #r=get_search_find_number(sor,200)

    #filter    
    diff_multi = get_search_time_ms_multi(event_list)
    return diff_multi

def experiment_dir_analyzer_multi(exp_dir):
    global csv_file   
    nodes_dir = "%s/nodes" % exp_dir
    master_dir = "%s/master" % exp_dir
    
    tmp = _get_subdirs(nodes_dir)
    run_list = []
    for i in tmp:
        if i.find("run_")!=-1:
            run_list.append(i)
    
    # temp. fixed run definition
    num = len(run_list)
    
    print "Found %d Runs of that experiment" % len(run_list)
    print "Summarizing each run..."
    result = []
    
    for j in range(exp.factor_list[1].levels.get_len()):
        for i in range(exp.factor_list[3].levels.get_len()):
            run = "run_0_%d_0_%d" %(j,i)
            result.append(run_dir_analyzer_multi(nodes_dir, run))
    
	fail_cnt = 0.0
#	for i in result:
#        if i<10:i
#            fail_cnt = fail_cnt + 1
#	print "Fails in this traffic level: %d/%d, Fail Percentage: %f (0..1)" % (fail_cnt,len(result), fail_cnt/len(result))

    fd=open(csv_file,"w")
    print result[0]
    i = 0
    for key,value in result[0].items():
        fd.write("%s"%key)
        if i == len(result[0])-1:
            fd.write("\n")
        else:
            fd.write(",")
        i = i + 1
    s = ""
    i = 0
    for (i,val) in enumerate(result):
        i = 0
        for key,val1 in val.items():
            #print "key,val", key,val1
            if i < len(val)-1:
                fd.write("%s," % (val1))
            else:
                fd.write("%s\n" % (val1))   
            i = i +1 
    fd.close()
    #print "Fails total: %d/%d, Fail Percentage: %f (0..1)" % (fail_cnt,len(result), fail_cnt/len(result))

def experiment_dir_analyzer(exp_dir):
    global csv_file
    global exp
    nodes_dir = "%s/nodes" % exp_dir
    master_dir = "%s/master" % exp_dir
    
    tmp = _get_subdirs(nodes_dir)
    run_list = []
    for i in tmp:
        if i.find("run_")!=-1:
            run_list.append(i)
    
    # temp. fixed run definition
    num = len(run_list)
    
    print "Found %d Runs of that experiment" % len(run_list)
    print "Summarizing each run..."
    result = []
    n = 1
    
    for j in range(exp.factor_list[1].levels.get_len()):
        for i in range(exp.factor_list[3].levels.get_len()):
            run = "run_0_%d_0_%d" %(j,i)
            result.append(run_dir_analyzer(nodes_dir, run))
    
        for deadline in range(300):
            get_responsiveness(result)
                    
    fail_cnt = 0.0
    for i in result:
        if i<10:
            fail_cnt = fail_cnt + 1
    print "Fails in this traffic level: %d/%d, Fail Percentage: %f (0..1)" % (fail_cnt,len(result), fail_cnt/len(result))

    fd=open(csv_file,"w")
    fd.write("val\n")
    for i in result:
        fd.write("%s\n" % (i)) 
    fd.close()
    #print "Fails total: %d/%d, Fail Percentage: %f (0..1)" % (fail_cnt,len(result), fail_cnt/len(result))

def run_analyzer(run_id, node, c):
    
    c.execute("SELECT CommonTime FROM Events WHERE runID=? and nodeID=? and EventType='sd_start_search'", [run_id,node['real_id']] )
    start_search_time = c.fetchone()[0]
    c.execute("SELECT CommonTime FROM Events WHERE runID=? and nodeID=? and EventType='sd_service_add'", [run_id,node['real_id']] )
    find_result = c.fetchone()
    if find_result==None:
        print "nothing found"
        return 
    print "start: ",start_search_time
    print "find:  ", find_result[0]
    
def get_responsiveness(run_id, node, deadline):
    c.execute("SELECT CommonTime FROM Events WHERE runID=? and nodeID=? and EventType='sd_start_search'", [run_id,node['real_id']] )
    start_search_time = c.fetchone()[0]
    c.execute("SELECT CommonTime FROM Events WHERE runID=? and nodeID=? and EventType='sd_service_add'", [run_id,node['real_id']] )
    find_result = c.fetchone()
    if find_result==None:
        #print "0"
        return 0
    start = db_timestamp_to_datetime(start_search_time)
    stop  = db_timestamp_to_datetime(find_result[0])
    #print stop-start, deadline
    if stop-start>datetime.timedelta(milliseconds=deadline):
        #print 0
        return 0
    else:
        #print 1
        return 1
    
def get_delay(run_id, node, services_needed):
    ''' 
    gets the search --> add delay from the event list
    '''
    c.execute("SELECT CommonTime FROM Events WHERE runID=? and nodeID=? and EventType='sd_start_search'", [run_id,node['real_id']] )
    start_search_time = c.fetchone()[0]
    c.execute("SELECT CommonTime FROM Events WHERE runID=? and nodeID=? and EventType='sd_service_add'", [run_id,node['real_id']] )
    find_result = c.fetchall()

    if find_result==None:
        return 2*deadline_events
    elif len(find_result) < services_needed:
        return 2*deadline_events
    else:
        stop_search_time = find_result[services_needed-1][0]
        start = db_timestamp_to_datetime(start_search_time)
        stop  = db_timestamp_to_datetime(stop_search_time)
        delay = stop-start
        #print delay.seconds*1000 + delay.microseconds / 1000
        delsec = delay.seconds*1000 + delay.microseconds / 1000
        return delsec
     
def get_delay_multi(run_id, node, number, deadline_ms):
    ''' gets the search --> add delay from the event list
    '''
    c.execute("SELECT CommonTime FROM Events WHERE runID=? and nodeID=? and EventType='sd_start_search' ORDER BY CommonTime ASC", [run_id,node['real_id']] )
    start_search_time = c.fetchone()[0]
    c.execute("SELECT CommonTime FROM Events WHERE runID=? and nodeID=? and EventType='sd_service_add'  ORDER BY CommonTime ASC", [run_id,node['real_id']] )
    find_result = c.fetchall()
    if find_result==None:
        #print "0"
        return deadline_ms
    start = db_timestamp_to_datetime(start_search_time)
    #stop  = start+datetime.timedelta(seconds=30)#
    if len(find_result)<number:
        return deadline_ms
        
    start = db_timestamp_to_datetime(start_search_time)
    stop  = db_timestamp_to_datetime(find_result[number-1][0])
    delay = stop-start
    #print delay.seconds*1000 + delay.microseconds / 1000
    return delay.seconds*1000 + delay.microseconds / 1000 

def get_delay_packets(run_id, client_node, provider_node):
    
    global exp
    max_retries = 5
     
    c.execute("SELECT CommonTime FROM Events WHERE runID=? and nodeID=? and EventType='sd_start_search'", [run_id,client_node['real_id']] )
    start_search_time = c.fetchone()[0]
    c.execute("SELECT * FROM Events WHERE runID=? and nodeID=? and EventType='sd_service_add'", [run_id,client_node['real_id']] )
    results = c.fetchall()
    #Cannot access table parameter because of name
    find_result = None
    for result in results:    
        if result[4] == provider_node['real_id'] + '\n':
            find_result=result
            break
    if find_result==None:
        return (max_retries,[2*deadline_packets]) # retries is -1 since the service was not found
    else:
        start = db_timestamp_to_datetime(start_search_time)
        stop = start + datetime.timedelta(milliseconds=deadline_packets)
        
        c.execute("SELECT * FROM Packets WHERE RunID=? and NodeID=? and SrcNodeID=? ORDER BY CommonTime ASC", [run_id, client_node['real_id'],client_node['real_id']])
        rows_sent = c.fetchall()
        c.execute("SELECT * FROM Packets WHERE RunID=? and NodeID=? and SrcNodeID=? ORDER BY CommonTime ASC", [run_id, client_node['real_id'],provider_node['real_id']])
        rows_recv = c.fetchall()
        
        # consider only send packets within the search/timeout interval
        for sent in list(rows_sent):
            sent_time = db_timestamp_to_datetime(sent[2])
            if sent_time < start or sent_time>stop:
                rows_sent.remove(sent)
        
        # consider only received packets within the search/timeout interval, also, consider only responses
        pkt_analyzer = packet_analyzer()
        for received in list(rows_recv):
            received_time = db_timestamp_to_datetime(received[2])
        
            # mdns flag say, if response or not, must be response
            pkt = received[4]
            ip=pkt_analyzer.decode_ip_packet(pkt)
            udp=pkt_analyzer.decode_udp_packet(ip['data'])
            mdns=pkt_analyzer.decode_mdns_packet(udp['data'])
            
            #if received_time < start or received_time > stop or mdns['flags'] & 128!=128:
            if mdns['flags'] & 128!=128:
                rows_recv.remove(received)
                
        packet_response=[]
        retry_cnt = 0
        
        for received in rows_recv:
            pkt_recv = received[4]        
            id_recv  = socket.ntohs(struct.unpack('H',pkt_recv[28:30])[0])
            
            for sent in rows_sent:
                pkt_sent = sent[4]
                id_sent = socket.ntohs(struct.unpack('H',pkt_sent[28:30])[0])
                    
                if id_recv==id_sent:                
                    t_sent = db_timestamp_to_datetime(sent[2])
                    t_recv = db_timestamp_to_datetime(received[2])
                    delay = t_recv - t_sent
                    packet_response.append(delay.seconds*1000 + delay.microseconds / 1000)
                    break
                packet_response.append(2*deadline_packets)
                retry_cnt = retry_cnt + 1
                    
    return (retry_cnt, packet_response)

def get_reqresp_delay(run_id, node):
    # first get start/stop times
    c.execute("SELECT CommonTime FROM Events WHERE runID=? and nodeID=? and EventType='sd_start_search'", [run_id,node['real_id']] )
    rows = c.fetchone()
    if rows==None:
        print "Error, no search found in run ", run_id, node['real_id']
        return -1
    
    start_search_time = rows[0]
    c.execute("SELECT CommonTime FROM Events WHERE runID=? and nodeID=? and EventType='sd_service_add'", [run_id,node['real_id']] )
    find_result = c.fetchone()
    if find_result==None:
        #print "0"
        return deadline_ms
    start = db_timestamp_to_datetime(start_search_time)
    #stop  = start+datetime.timedelta(seconds=30)#
    stop  = db_timestamp_to_datetime(find_result[0])
    
def check_packets_multi(run_id, node, deadline_ms, desired_number):
    '''
    Steps: First select packets of this run, "sent" and "received". "sent" is to be handled with care, as previously sent packets
    can be received again and have to be filtered out. This unfortunately can also be packets from other runs.
    When a packet from another run is detected as sent, it can be removed from the list, when a response arrives
    within the search window, then this search is false positive and must FAIL.
    '''
    # first get start/stop times
    c.execute("SELECT CommonTime FROM Events WHERE runID=? and nodeID=? and EventType='sd_start_search'", [run_id,node['real_id']] )
    rows = c.fetchone()
    if rows==None:
        print "Error, no search found in run ", run_id, node['real_id']
        return -1
    
    start_search_time = rows[0]
    c.execute("SELECT CommonTime FROM Events WHERE runID=? and nodeID=? and EventType='sd_service_add'", [run_id,node['real_id']] )
    find_result = c.fetchall()
    if find_result==None:
        #print "0"
        stop  = start+datetime.timedelta(milliseconds=deadline_ms)
    start = db_timestamp_to_datetime(start_search_time)
    #stop  = start+datetime.timedelta(seconds=30)#
    if len(find_result)<desired_number:
        stop = start+datetime.timedelta(seconds=30)
    else:
        stop  = db_timestamp_to_datetime(find_result[desired_number-1][0])
        if stop > start+datetime.timedelta(milliseconds=deadline_ms):
            stop = start+datetime.timedelta(milliseconds=deadline_ms)                     
    #print start
    #print stop

    c.execute("SELECT * FROM Packets WHERE RunID=? and NodeID=? and SrcNodeID=?  ORDER BY CommonTime ASC", [run_id, node['real_id'],node['real_id']])
    rows_send = c.fetchall()
    #print rows_send
    c.execute("SELECT * FROM Packets WHERE RunID=? and NodeID=? and SrcNodeID!=?  ORDER BY CommonTime ASC", [run_id, node['real_id'],node['real_id']])
    rows_recv = c.fetchall()
    #print rows_recv
    # consider only packets within the search/timeout interval
    for sent in list(rows_send):
        sent_time = db_timestamp_to_datetime(sent[2])
        if sent_time < start or sent_time>stop:
            rows_send.remove(sent)
    '''
    Only responses are considered, for that reason create an instance of 
    the packet_analyzer that will be used to process each of the rows 
    since the information about if the row is a response or not is contained
    in the mdns flag.
    '''      
    pkt_analyzer = packet_analyzer()
    #print start
    #print stop
    for received in list(rows_recv):
        received_time = db_timestamp_to_datetime(received[2])
        pkt = received[4]
        ip=pkt_analyzer.decode_ip_packet(pkt)
        udp=pkt_analyzer.decode_udp_packet(ip['data'])
        mdns=pkt_analyzer.decode_mdns_packet(udp['data'])
        '''mdns flag say, if response or not, must be response'''
        if received_time < start or received_time > stop or mdns['flags'] & 128!=128:
            #print "removing", received
            rows_recv.remove(received)
            
    '''
    list packets by their transaction ID
    remove duplicates and out of order packets from the sent
    '''
    sent_by_id =  {}
    for i,sent in enumerate(list(rows_send)):      
        pkt = sent[4]        
        id  = socket.ntohs(struct.unpack('H',pkt[28:30])[0])
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
        id  = socket.ntohs(struct.unpack('H',pkt[28:30])[0])
        #print "ResponseID: %d" %id
        found = 0
        for id_sent,sent in sent_by_id.items():
            if id==id_sent:
                #print "found same IDs", id
                found = 1
                t_requ = db_timestamp_to_datetime(sent[2])
                t_resp = db_timestamp_to_datetime(received[2])
                delay = t_resp - t_requ
                #return delay.seconds*1000 + delay.microseconds / 1000
        if found==0:
            #print "Fail Runid=%s" %run_id, received
            return -1
                
    return 0

def check_packets_return_retries(run_id, node, deadline_ms):
    '''
    Steps: First select packets of this run, "sent" and "received". "sent" is to be handled with care, as previously sent packets
    can be received again and have to be filtered out. This unfortunately can also be packets from other runs.
    When a packet from another run is detected as sent, it can be removed from the list, when a response arrives
    within the search window, then this search is false positive and must FAIL.
    '''
        
    # first get start/stop times
    c.execute("SELECT CommonTime FROM Events WHERE runID=? and nodeID=? and EventType='sd_start_search'", [run_id,node['real_id']] )
    rows = c.fetchone()
    if rows==None:
        print "Error, no search found in run ", run_id, node['real_id']
        return -1
    
    start_search_time = rows[0]
    start = db_timestamp_to_datetime(start_search_time)
    
    c.execute("SELECT CommonTime FROM Events WHERE runID=? and nodeID=? and EventType='sd_service_add'", [run_id,node['real_id']] )
    find_result = c.fetchone()
    if find_result==None:
        #print "0"
        stop  = start+datetime.timedelta(milliseconds=deadline_ms)
    else:
    #stop  = start+datetime.timedelta(seconds=30)#
        stop  = db_timestamp_to_datetime(find_result[0])
        if stop > start+datetime.timedelta(milliseconds=deadline_ms):
            stop = start+datetime.timedelta(milliseconds=deadline_ms)
                                                
    #print start
    #print stop

    c.execute("SELECT * FROM Packets WHERE RunID=? and NodeID=? and SrcNodeID=? ORDER BY CommonTime ASC", [run_id, node['real_id'],node['real_id']])
    rows_send = c.fetchall()
    #print rows_send
    c.execute("SELECT * FROM Packets WHERE RunID=? and NodeID=? and SrcNodeID!=? ORDER BY CommonTime ASC", [run_id, node['real_id'],node['real_id']])
    rows_recv = c.fetchall()
    #print rows_recv
    # consider only packets within the search/timeout interval
    
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
    sent_by_id =  {}
    for i,sent in enumerate(list(rows_send)):      
        pkt = sent[4]        
        id  = socket.ntohs(struct.unpack('H',pkt[28:30])[0])
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
        id  = socket.ntohs(struct.unpack('H',pkt[28:30])[0])
        #print "ResponseID: %d" %id
        found = 0
        retry_cnt = 0
        for id_sent,sent in sent_by_id.items():
            if id==id_sent:
                #print "found same IDs", id
                found = 1
                
                t_requ = db_timestamp_to_datetime(sent[2])
                t_resp = db_timestamp_to_datetime(received[2])
                delay = t_resp - t_requ
                return (retry_cnt,delay.seconds*1000 + delay.microseconds / 1000)
            retry_cnt = retry_cnt + 1
        if found==0:
            #print "Fail Runid=%s" %run_id, received
            return (-1,-1)
               
    #for id_send, sent in sent_by_id.items():
    #    for received in rows_recv:
    #        pkt = received[4]
    #        id  = socket.ntohs(struct.unpack('H',pkt[28:30])[0])
    ##        #print "ResponseID: %d" %id
    #        found = 0  
    return (-1,deadline_ms)


#Checks for validity of the routes from the ExtraRunMeasurements
def check_route(run_id, node):    

#     c.execute("SELECT Content FROM ExtraRunMeasurements WHERE runID=? and nodeID=?", [run_id,node['real_id']] )
    c.execute("SELECT Content FROM ExtraRunMeasurements WHERE runID=? and nodeID=?", [run_id,node['real_id']] )
    routes = str(c.fetchone())
    if 'fail' in routes :
#         print run_id,node['real_id']
#         print " invalid run"
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
    
#     if fails > 0:
#         print "Run %d, Failed routes %s" % (run_id, fails)

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
    rows = c.fetchone()
    if rows==None:
        print "Error, no search found in run ", run_id, node['real_id']
        return -1
    
    start_search_time = rows[0]
    start = db_timestamp_to_datetime(start_search_time)
    c.execute("SELECT CommonTime FROM Events WHERE runID=? and nodeID=? and EventType='sd_service_add'", [run_id,node['real_id']] )
    find_result = c.fetchone()
    if find_result==None:
        #print "0"
        stop  = start+datetime.timedelta(milliseconds=deadline_ms)
    else:
        stop  = db_timestamp_to_datetime(find_result[0])
        if stop > start+datetime.timedelta(milliseconds=deadline_ms):
            stop = start+datetime.timedelta(milliseconds=deadline_ms)

    c.execute("SELECT * FROM Packets WHERE RunID=? and NodeID=? and SrcNodeID=? ORDER BY CommonTime ASC", [run_id, node['real_id'],node['real_id']])
    rows_send = c.fetchall()
    #print rows_send
    c.execute("SELECT * FROM Packets WHERE RunID=? and NodeID=? and SrcNodeID!=?  ORDER BY CommonTime ASC", [run_id, node['real_id'],node['real_id']])
    rows_recv = c.fetchall()
    #print rows_recv
    # consider only packets within the search/timeout interval
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
    sent_by_id =  {}
    for i,sent in enumerate(list(rows_send)):      
        pkt = sent[4]        
        id  = socket.ntohs(struct.unpack('H',pkt[28:30])[0])
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
        id  = socket.ntohs(struct.unpack('H',pkt[28:30])[0])
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

def check_single_search_paket_ok():
    '''    
    '''
    global conn
    
    c = conn.cursor()
    delay = []
    for i in range(300):
        delay.append(0)
    
    #loop over run sequence
    fail = 0
    for run_number in range(exp.get_run_count()):
        ###### SETUP LEVELS OF ALL FACTORS FOR THIS RUN ########
        exp.set_run_number(run_number)
        run_definition = exp.get_run_identifier()
        #print "run_definition", run_definition
        c.execute("SELECT RunID FROM run_ids WHERE run_identifier=?",[run_definition])
        run_id = c.fetchone()[0]
        
        
        all_nodes = exp.get_all_spec_nodes()
        for node in all_nodes:
            if node['real_id']=="t9-007":
                if get_packet(run_id, node)==-1:
                    fail = fail + 1
    
    conn.commit()
    
def get_time_offset(run_id, node):
    '''
    retrieves the offset of the current node to the reference clock as measured by ExperiMaster
    '''
    c.execute("SELECT TimeDiff FROM RunInfos WHERE runID=? and nodeID=?", [run_id,node['real_id']] )
    rows = c.fetchone()
    if rows==None:
        print "Error, no search found in run ", run_id, node['real_id']
        return -1000
    return rows[0]

def write_to_csv(data):
    
    fd=open(csv_file,"w")
    for row in data:
        #if len(data)>0:
        #    for col in data:
        #        fd.write("%f,"%col)
        #else:
        fd.write("%f\n"%row)
    fd.close()

def write_to_csv_filename(data,filename):
    
    fd=open(filename,"w")
    for row in data:
        fd.write("%f\n"%row)
    fd.close()

def print_plot_cdf(fig,ax,xdata,ydata,xscale,deadline):
    
    global data_num
    global figures
    colors=['black','red','blue','green','yellow','purple','gray']
    linestyles=['-','--','-.',':','-','--','-.',':']

    fn_split=fn.split("_")
    if int(fn_split[3]) > 0:
        legend_string = "%d VoIP Streams Load" % int(fn_split[3])
    else:
        legend_string = "No Load"

    ax.xaxis.set_major_locator(ScaledLocator(dx=xscale))
    ax.xaxis.set_major_formatter(ScaledFormatter(dx=xscale))
    
    ax.plot(xdata, ydata, drawstyle='steps',linestyle=linestyles[data_num], color=colors[data_num], label=legend_string)
    ax.set_xlabel('Deadline in ms',{'fontsize':'x-large'})
    ax.set_ylabel('Responsiveness',{'fontsize':'x-large'})
    ax.legend(loc = "lower right")
    
    ax.grid(True)
    ax.set_ylim([0,1])
    ax.set_xlim([0,deadline])
    ax.hold(True)
    if fig not in figures:
        figures.append(fig)

def print_plot_pdf(fig,ax,data,bins,weights,xscale,deadline):
    
    global data_num
    global figures
    colors=['black','red','blue','green','yellow','purple','gray']
    
    fn_split=fn.split("_")
    if int(fn_split[3]) > 0:
        legend_string = "%d VoIP Streams Load" % int(fn_split[3])
    else:
        legend_string = "No Load"

    ax.xaxis.set_major_locator(ScaledLocator(dx=xscale))
    ax.xaxis.set_major_formatter(ScaledFormatter(dx=xscale))

    ax.hist(data, bins=bins, normed=False, weights=weights, histtype='stepfilled',color=colors[data_num], alpha=0.5,label=legend_string)
    ax.set_xlabel('Time in ms',{'fontsize':'x-large'})
    ax.set_ylabel('Probability',{'fontsize':'x-large'})
    ax.legend(loc = "upper right")
    
    ax.grid(True)
    ax.set_ylim([0,1])
    ax.set_xlim([0,deadline])
    ax.hold(True)
    if fig not in figures:
        figures.append(fig)

def print_plot_packet_retries(type):
    
    plt.xlabel('Retries',{'fontsize':'x-large'})
    plt.ylabel('Responsiveness',{'fontsize':'x-large'})
    plt.grid(True)
    if type == 'cdf':
        plt.legend(loc = "lower right")
    else:
        plt.legend(loc = "upper right")
    plt.xlim([0,5])
    plt.hold(True)
    
    savename = "plot.pdf"
    plt.savefig(savename, dpi=600)

''' ----------------Analysis Methods-----------------'''

def experiment_analyzer_single():
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
        delay.append([])
        pkt_delay.append([])
        for i in range(exp.get_run_count()):
            delay[n].append(deadline)
            pkt_delay[n].append(dealine)
              
    #loop over run sequence
    fail = 0
    succeeded = 0
    timedout = 0
    valid_results = [0,0,0,0]
    
    num_responders = len(exp.get_responders())
    services_needed = min(num_responders, int(round(sdratio * num_responders) / 100 + 0.5))
    
    for run_number in range(exp.get_run_count()):
        ###### SETUP LEVELS OF ALL FACTORS FOR THIS RUN ########
        exp.set_run_number(run_number)
        run_definition = exp.get_run_identifier()
        #print "exporting run number %d with combination %s" %(run_number,run_definition)
        #print "run_definition", run_definition
        c.execute("SELECT RunID FROM run_ids WHERE run_identifier=?",[run_definition])
        run_id = c.fetchone()[0]
        
        fact = exp.get_current_factor_level_by_id('fact_pairs')
        run_fact = exp.get_current_factor_level_by_id('fact_replication_id')
        all_nodes = exp.get_all_spec_nodes()
        for node in all_nodes:
            if node['real_id']==exp.get_requester()["real_id"]:
                #events=run_analyzer(run_id,node,c)
                #for deadline in range(30):
                #    resp[deadline] = resp[deadline] + get_responsiveness(run_id, node, deadline*1000)
                #delay[run_number] = get_delay(run_id, node)
                res=check_packets(run_id, node, 30000)
                if res==-1:
                    fail = fail + 1
                else:
                    index=valid_results[fact]
                    delay[fact][index] = get_delay(run_id,node)
                    #if (res==30000):
                    #    res=0
                    #pkt_delay[fact][index] = res
                    valid_results[fact] = valid_results[fact] + 1
            

    ######## RESPONSIVENESS 1zu1 ############
    print "Valid: ",valid_results
    print "Fail: ",fail
    #for i in range(250):    
    #    print delay[3][i]
    symbols = ['k-','k--','k-.','k:']
    for fact in range(4):
        res = []
        
        for i in range(60000):
            ok = 0
            for n in range(valid_results[fact]):
                if pkt_delay[fact][n]<i:
                    ok = ok + 1
            res.append((ok*100/valid_results[fact])*0.01)
        plt.plot(res,symbols[fact])
        plt.xlabel('Deadline in ms',{'fontsize':'x-large'})
        plt.ylabel('Responsiveness',{'fontsize':'x-large'})
        plt.legend(('no load', '26 VoIP', '53 VoIP', '80 VoIP'),
           'right', shadow=True)
        #plt.grid(True)
        plt.ylim([0,1.1])
        plt.savefig("/tmp/image300.png", dpi=300)
         
    plt.show()
    #########################################
    
    ##### Paket delays ######################
    #symbols = ['ko','k^','k-.','k:']
    #for fact in range(4):
    #    res = []
        #print pkt_delay[fact]
        #for i in range(300):
            #ok = 0
            #for n in range(valid_results[fact]):
            #    if delay[fact][n]<i*100:
            #        ok = ok + 1
            #res.append((ok*100/valid_results[fact])*0.01)
    #    plt.plot(pkt_delay[fact],symbols[fact])
    #    plt.xlabel('runs')
    #    plt.ylabel('Request/Response delay')
    #    plt.legend(('no load', '26 VoIP', '53 VoIP', '80 VoIP'),
     #      'right', shadow=True)
    #    plt.grid(True)
    #    plt.savefig("/tmp/image2300.png", dpi=300)
        
        
    #plt.show()
    
    #r=get_search_find_number(sor,200)

    #filter
    #diff= get_search_time_ms(event_list)
    conn.commit()

def experiment_analyzer_multi():
    '''
    '''
    global conn
    global exp
    
    c = conn.cursor()
    delay = []
  
    for n in range(4):
        delay.append([])
        for i in range(exp.get_run_count()):
            delay[n].append(30000)
            
    print len(delay)
    
    #loop over run sequence
    fail = 0
    valid_results = [0,0,0,0]
    
    for run_number in range(exp.get_run_count()):
        ###### SETUP LEVELS OF ALL FACTORS FOR THIS RUN ########
        exp.set_run_number(run_number)
        run_definition = exp.get_run_identifier()
        #print "exporting run number %d with combination %s" %(run_number,run_definition)
        #print "run_definition", run_definition
        c.execute("SELECT RunID FROM run_ids WHERE run_identifier=?",[run_definition])
        run_id = c.fetchone()[0]
        
        fact = exp.get_current_factor_level_by_id('fact_pairs')
        run_fact = exp.get_current_factor_level_by_id('fact_replication_id')
        all_nodes = exp.get_all_spec_nodes()
        for node in all_nodes:
            if node['real_id']==exp.get_requester()["real_id"]:
                #events=run_analyzer(run_id,node,c)
                #for deadline in range(30):
                #    resp[deadline] = resp[deadline] + get_responsiveness(run_id, node, deadline*1000)
                #delay[run_number] = get_delay(run_id, node)
                res=check_packets_multi(run_id, node, 30000, 10)
                if res==-1:
                    fail = fail + 1
                else:
                    delay[fact][run_fact] = get_delay(run_id,node)
                    valid_results[fact] = valid_results[fact] + 1
                
    #find fails
        #if run_number==249: print "Failed: %d" % fail
        #if run_number==499: print "Failed: %d" % fail
        #if run_number==749: print "Failed: %d" % fail
        #if run_number==999: print "Failed: %d" % fail
    ######## RESPONSIVENESS 1zu1 ############
    print "Valid: ",valid_results
    
    #for i in range(250):    
    #    print delay[3][i]
    
    symbols = ['k-','k:','k--','k-.']
    for fact in range(4):
        res = []
        
        for i in range(3000):
            ok = 0
            for n in range(valid_results[fact]):
                if delay[fact][n]<i*10:
                    ok = ok + 1
            res.append((ok*100/valid_results[fact])*0.01)
        
        plt.plot(res,symbols[fact])
        plt.xlabel('Deadline in ms')
        plt.ylabel('Responsiveness')
        plt.legend(('no load', '26 VoIP', '53 VoIP', '80 VoIP'),
           'right', shadow=True)
        plt.grid(True)
        plt.ylim([0,1.1])
        #plt.savefig("image300.png")
        #plt.savefig('/tmp/image100.png', dpi=100)
 
    #plt.show()
    #########################################
    
    #r=get_search_find_number(sor,200)

    #filter
    #diff= get_search_time_ms(event_list)
    conn.commit()

def get_responsiveness_single():
    '''    
    '''
    global conn
    global exp
    
    c = conn.cursor()
    delay = []
    pkt_delay = []
    time_offset = []
    for n in range(4):
        delay.append([])
        pkt_delay.append([])
        for i in range(exp.get_run_count()):
            delay[n].append(30000)
            pkt_delay[n].append(30000)
              
    #loop over run sequence
    fail = 0
    valid_results = [0,0,0,0]
    
    for run_number in range(exp.get_run_count()):
        ###### SETUP LEVELS OF ALL FACTORS FOR THIS RUN ########
        exp.set_run_number(run_number)
        run_definition = exp.get_run_identifier()
        #print "exporting run number %d with combination %s" %(run_number,run_definition)
        #print "run_definition", run_definition
        c.execute("SELECT RunID FROM run_ids WHERE run_identifier=?",[run_definition])
        run_id = c.fetchone()[0]
        
        fact = exp.get_current_factor_level_by_id('fact_pairs')
        run_fact = exp.get_current_factor_level_by_id('fact_replication_id')
        all_nodes = exp.get_all_spec_nodes()
        for node in all_nodes:
            if node['real_id']==exp.get_requester()["real_id"]:

                res=check_packets(run_id, node, 30000)
                if res==-1:
                    fail = fail + 1
                else:
                    index=valid_results[fact]
                    delay[fact][index] = get_delay(run_id,node)
                    #if (res==30000):
                    #    res=0
                    pkt_delay[fact][index] = res
                    valid_results[fact] = valid_results[fact] + 1
            

    ######## RESPONSIVENESS 1zu1 ############
    print "Valid: ",valid_results
    print "Fail: ",fail
    #for i in range(250):    
    #    print delay[3][i]
    symbols = ['k-','k--','k-.','k:']
    for fact in range(4):
        res = []
        
        for i in range(30000):
            ok = 0
            for n in range(valid_results[fact]):
                if delay[fact][n]<i*1:
                    ok = ok + 1
            res.append((ok*100/valid_results[fact])*0.01)
        plt.plot(res,symbols[fact])
        plt.xlabel('Deadline in ms',{'fontsize':'x-large'})
        plt.ylabel('Responsiveness',{'fontsize':'x-large'})
        plt.legend(('no load', '26 VoIP', '53 VoIP', '80 VoIP'),
           'right', shadow=True)
        #plt.grid(True)
        plt.ylim([0,1.1])
        plt.savefig("/tmp/image300.png", dpi=200)
    plt.show()
    conn.commit()
    
def get_responsiveness_multi():
    '''
    '''
    global conn
    global exp
    
    c = conn.cursor()
    delay = []
    pkt_delay = []
    time_offset = []
    for n in range(4):
        delay.append([])
        pkt_delay.append([])
        for i in range(exp.get_run_count()):
            delay[n].append(30000)
            pkt_delay[n].append(30000)
              
    #loop over run sequence
    fail = 0
    valid_results = [0,0,0,0]
    number = 9
    for run_number in range(exp.get_run_count()):
        ###### SETUP LEVELS OF ALL FACTORS FOR THIS RUN ########
        exp.set_run_number(run_number)
        run_definition = exp.get_run_identifier()
        #print "exporting run number %d with combination %s" %(run_number,run_definition)
        #print "run_definition", run_definition
        c.execute("SELECT RunID FROM run_ids WHERE run_identifier=?",[run_definition])
        run_id = c.fetchone()[0]
        
        fact = exp.get_current_factor_level_by_id('fact_pairs')
        run_fact = exp.get_current_factor_level_by_id('fact_replication_id')
        all_nodes = exp.get_all_spec_nodes()
        for node in all_nodes:
            if node['real_id']==exp.get_requester()["real_id"]:

                res=check_packets_multi(run_id, node, number, 30000)
                if res==-1:
                    fail = fail + 1
                else:
                    index=valid_results[fact]
                    delay[fact][index] = get_delay_multi(run_id,node,number,30000)
                    #if delay[fact][index]>30000:
                    #    delay[fact][index]=30000
                    #if (res==30000):
                    #    res=0
                    #pkt_delay[fact][index] = res
                    valid_results[fact] = valid_results[fact] + 1

    ######## RESPONSIVENESS 1zu1 ############
    print "Valid: ",valid_results
    print "Fail: ",fail
    #for i in range(250):    
    #    print delay[3][i]
    #plt.plot(delay[1])
    #plt.show()
    symbols = ['k-','k--','k-.','k:']
    for fact in range(4):
        res = []
        
        for i in range(30000):
            ok = 0
            for n in range(valid_results[fact]):
                if delay[fact][n]<i*1:
                    ok = ok + 1
                else:
                    pass#print delay[fact][n], i
            #print ok, valid_results[fact]
            res.append((ok*100/valid_results[fact])*0.01)
        plt.plot(res,symbols[fact])
        plt.xlabel('Deadline in ms',{'fontsize':'x-large'})
        plt.ylabel('Responsiveness',{'fontsize':'x-large'})
        plt.legend(('no load', '26 VoIP', '53 VoIP', '80 VoIP'),
           'best',shadow=True)
        #plt.grid(True)
        plt.ylim([0,1.1])
        plt.savefig("/tmp/multi_responsiveness.png", dpi=200)
    plt.show()
    conn.commit()
    
def response_delays_single():
    '''    
    '''
    global conn
    global exp
    
    c = conn.cursor()
    delay = []
    pkt_delay = []
    time_offset = []
    for n in range(4):
        delay.append([])
        pkt_delay.append([])
        for i in range(exp.get_run_count()/4):
            delay[n].append(32000)
            pkt_delay[n].append(32000)
              
    #loop over run sequence
    fail = 0
    valid_results = [0,0,0,0]
    flat = []
    flat2 = []
    for run_number in range(exp.get_run_count()):
        ###### SETUP LEVELS OF ALL FACTORS FOR THIS RUN ########
        exp.set_run_number(run_number)
        run_definition = exp.get_run_identifier()
        #print "exporting run number %d with combination %s" %(run_number,run_definition)
        #print "run_definition", run_definition
        c.execute("SELECT RunID FROM run_ids WHERE run_identifier=?",[run_definition])
        run_id = c.fetchone()[0]
        
        fact = exp.get_current_factor_level_by_id('fact_pairs')
        run_fact = exp.get_current_factor_level_by_id('fact_replication_id')
        all_nodes = exp.get_all_spec_nodes()
        for node in all_nodes:
            if node['real_id']==exp.get_requester()["real_id"]:
                retry_count,res=check_packets_return_retries(run_id, node, 30000)

                if res==-1:
                    fail = fail + 1
                else:
                    valid_results[fact] = valid_results[fact] + 1
                    delay=get_delay(run_id,node)
                    if delay>30000:
                        delay=30000
                    flat.append(delay)
                    flat2.append(res)
    
    symbols = ['ko','k^','k-.','k:']
    plt.plot(flat,'ko', markersize=2)
    #plt.plot(flat,'ko', markersize=0.4)    
    plt.xlabel('runs')
    plt.ylabel('Discovery delay')
    #plt.legend(('no load', '26 VoIP', '53 VoIP', '80 VoIP'),
    #   'right', shadow=True)
    #plt.grid(True)
    plt.ylim([0,31000])
    plt.xlim([0,1000])
    plt.savefig("/tmp/sd_delay.png", dpi=200)
    plt.show()
    conn.commit()
    
def response_delays_multi():
    '''
    '''
    global conn
    global exp
    
    c = conn.cursor()
    delay = []
    pkt_delay = []
    time_offset = []
    for n in range(4):
        delay.append([])
        pkt_delay.append([])
        for i in range(exp.get_run_count()/4):
            delay[n].append(32000)
            pkt_delay[n].append(32000)
              
    #loop over run sequence
    fail = 0
    valid_results = [0,0,0,0]
    flat = []
    flat2 = []
    for run_number in range(exp.get_run_count()):
        ###### SETUP LEVELS OF ALL FACTORS FOR THIS RUN ########
        exp.set_run_number(run_number)
        run_definition = exp.get_run_identifier()
        #print "exporting run number %d with combination %s" %(run_number,run_definition)
        #print "run_definition", run_definition
        c.execute("SELECT RunID FROM run_ids WHERE run_identifier=?",[run_definition])
        run_id = c.fetchone()[0]
        
        fact = exp.get_current_factor_level_by_id('fact_pairs')
        run_fact = exp.get_current_factor_level_by_id('fact_replication_id')
        all_nodes = exp.get_all_spec_nodes()
        for node in all_nodes:
            if node['real_id']==exp.get_requester()["real_id"]:
                retry_count,res=check_packets_return_retries(run_id, node, 30000)

                if res==-1:
                    fail = fail + 1
                else:
                    valid_results[fact] = valid_results[fact] + 1
                    delay=get_delay_multi(run_id,node,10,30000)
                    if delay>30000:
                        delay=30000
                    flat.append(delay)
                    flat2.append(res)
    
    symbols = ['ko','k^','k-.','k:']
    plt.plot(flat,'ko', markersize=2)
    #plt.plot(flat,'ko', markersize=0.4)    
    plt.xlabel('runs')
    plt.ylabel('Discovery delay')
    #plt.legend(('no load', '26 VoIP', '53 VoIP', '80 VoIP'),
    #   'right', shadow=True)
    #plt.grid(True)
    plt.ylim([0,31000])
    plt.xlim([0,1000])
    plt.savefig("/tmp/sd_delay.png", dpi=200)
    plt.show()
    conn.commit()    
    
def experiment_analyzer_single_get_timediffs():
    '''
    '''
    global conn
    global exp
    
    c = conn.cursor()
    delay = []
    pkt_delay = []
    time_offset = []
    for n in range(4):
        delay.append([])
        pkt_delay.append([])
        time_offset.append([])
        for i in range(exp.get_run_count()/4):
            delay[n].append(30000)
            pkt_delay[n].append(30000)
            time_offset[n].append(1000)
            
    #for i in range(exp.get_run_count()):
    #d    time_offset_flat.append(1000)
    print len(delay)
    
    time_offset_flat = {}
    all_nodes = exp.get_all_spec_nodes()
    for node in all_nodes:
        #if node['real_id']==exp.get_requester()["real_id"] or node['real_id']=="t9-":
        if node['abstract_id']!="":
            print "node"
            time_offset_flat[node['abstract_id']]=[]
        
    #loop over run sequence
    fail = 0
    valid_results = [0,0,0,0]
    
    for run_number in range(exp.get_run_count()):
        ###### SETUP LEVELS OF ALL FACTORS FOR THIS RUN ########
        exp.set_run_number(run_number)
        run_definition = exp.get_run_identifier()
        #print "exporting run number %d with combination %s" %(run_number,run_definition)
        #print "run_definition", run_definition
        c.execute("SELECT RunID FROM run_ids WHERE run_identifier=?",[run_definition])
        run_id = c.fetchone()[0]
        
        fact = exp.get_current_factor_level_by_id('fact_pairs')
        run_fact = exp.get_current_factor_level_by_id('fact_replication_id')
        all_nodes = exp.get_all_spec_nodes()
        for node in all_nodes:
            if node['abstract_id']!="":
                time_offset_flat[node['abstract_id']].append(get_time_offset(run_id, node))
    
    res = []
    absdiff = []
    for i in range(len(time_offset_flat['A'])):
        absdiff.append( abs(int(time_offset_flat['A'][i])-int(time_offset_flat['B'][i])) )
    plt.plot(time_offset_flat['A'],"k.")
    plt.plot(time_offset_flat['B'],"k:")
    plt.plot(absdiff, "k-")
    plt.xlabel('runs')
    plt.ylabel('Measured Time Offset')
    plt.legend(('Node A Offset', 'Node B Offset', 'absolute difference'),
       'bottom', shadow=True)
    plt.grid(False)
    plt.ylim([-100,60])
    plt.savefig("/tmp/timediff.png", dpi=300)
            
    plt.show()

    print time_offset
 
    conn.commit() 
    
def experiment_analyzer_multi_get_timediffs():
    '''
    '''
    global conn
    global exp
    
    c = conn.cursor()
    delay = []
    pkt_delay = []
    time_offset = []
    for n in range(4):
        delay.append([])
        pkt_delay.append([])
        time_offset.append([])
        for i in range(exp.get_run_count()/4):
            delay[n].append(30000)
            pkt_delay[n].append(30000)
            time_offset[n].append(1000)
            
    #for i in range(exp.get_run_count()):
    #d    time_offset_flat.append(1000)
    print len(delay)
    
    time_offset_flat = {}
    all_nodes = exp.get_all_spec_nodes()
    for node in all_nodes:
        #if node['real_id']==exp.get_requester()["real_id"] or node['real_id']=="t9-":
        if node['abstract_id']!="":
            print "node"
            time_offset_flat[node['abstract_id']]=[]
        
    #loop over run sequence
    fail = 0
    valid_results = [0,0,0,0]
    
    for run_number in range(exp.get_run_count()):
        ###### SETUP LEVELS OF ALL FACTORS FOR THIS RUN ########
        exp.set_run_number(run_number)
        run_definition = exp.get_run_identifier()
        #print "exporting run number %d with combination %s" %(run_number,run_definition)
        #print "run_definition", run_definition
        c.execute("SELECT RunID FROM run_ids WHERE run_identifier=?",[run_definition])
        run_id = c.fetchone()[0]
        
        fact = exp.get_current_factor_level_by_id('fact_pairs')
        run_fact = exp.get_current_factor_level_by_id('fact_replication_id')
        all_nodes = exp.get_all_spec_nodes()
        for node in all_nodes:
            if node['abstract_id']!="":
                time_offset_flat[node['abstract_id']].append(get_time_offset(run_id, node))
    
    res = []
    absdiff = []
    for key,timeline in time_offset_flat.items():
    #for i in range(len(time_offset_flat['A'])):
    #    absdiff.append( abs(int(time_offset_flat['A'][i])-int(time_offset_flat['B'][i])) )
        
        plt.plot(timeline, "-")
    
    #plt.plot(time_offset_flat['A'],"k.")
    #plt.plot(time_offset_flat['B'],"k:")
    #plt.plot(absdiff, "k-")
    plt.xlabel('runs')
    plt.ylabel('Measured Time Offset')
    plt.legend(('Node A Offset', 'Node B Offset', 'absolute difference'),
       'bottom', shadow=True)
    plt.grid(False)
    plt.ylim([-100,60])
    plt.savefig("/tmp/timediff.png", dpi=300)
    plt.show()
    print time_offset
    conn.commit()

def successful_query_delays_single():
    '''
    '''
    global conn
    global exp
    
    c = conn.cursor()
    delay = []
    pkt_delay = []
    time_offset = []
    for n in range(4):
        delay.append([])
        pkt_delay.append([])
        for i in range(exp.get_run_count()/4):
            delay[n].append(30000)
            pkt_delay[n].append(30000)
              
    #loop over run sequence
    fail = 0
    valid_results = [0,0,0,0]
    flat = []
    for run_number in range(exp.get_run_count()):
        ###### SETUP LEVELS OF ALL FACTORS FOR THIS RUN ########
        exp.set_run_number(run_number)
        run_definition = exp.get_run_identifier()
        #print "exporting run number %d with combination %s" %(run_number,run_definition)
        #print "run_definition", run_definition
        c.execute("SELECT RunID FROM run_ids WHERE run_identifier=?",[run_definition])
        run_id = c.fetchone()[0]
        
        fact = exp.get_current_factor_level_by_id('fact_pairs')
        run_fact = exp.get_current_factor_level_by_id('fact_replication_id')
        all_nodes = exp.get_all_spec_nodes()
        for node in all_nodes:
            if node['real_id']==exp.get_requester()["real_id"]:
                retry_count,res=check_packets_return_retries(run_id, node, 30000)
                
                if res==-1:
                    fail = fail + 1
                else:
                    flat.append(res)
    
    symbols = ['ko','k^','k-.','k:']
    #for fact in range(4):
     #   res = []
        #print pkt_delay[fact]
        #for i in range(300):
            #ok = 0
            #for n in range(valid_results[fact]):
            #    if delay[fact][n]<i*100:
            #        ok = ok + 1
            #res.append((ok*100/valid_results[fact])*0.01)
    plt.plot(flat,'ko', markersize=2)
    #plt.plot(flat2,'r-', markersize=0.4)    
    plt.xlabel('valid runs')
    plt.ylabel('successful request/response delay')
    plt.ylim([0,31000])
    plt.xlim([0,1000])
    #plt.legend(('no load', '26 VoIP', '53 VoIP', '80 VoIP'),
    #   'right', shadow=True)
    #plt.grid(True)
    plt.savefig("/tmp/requresp_delay.png", dpi=200)        
    plt.show()
    conn.commit()


def response_analysis(sdratio,dist_type):
    '''
    Method for obtaining the cumulative or probability distribution functions
    of the response times of the service discovery
    
    sdratio: percentage of service instances needed to be found
    type: type of analysis to perfomr, cdf or pdf
    '''
    global conn
    global exp
    global ax
    global fig_cdf, fig_pdf
    global ax_cdf, ax_pdf
    count = 0
    res = 0
    
    c = conn.cursor()
    delays_events = []
    delays_packets = []
    retries_packets = []
       
    ''' loop over run sequence '''
    fail = 0
    succeeded = [0,0]
    timedout = [0,0]
    valid_results = {'0':[0,0,0,0],'1':[0,0,0,0]}
    
    num_responders = len(exp.get_responders())
    services_needed = min(num_responders, int(round(sdratio * num_responders) / 100 + 0.5))
    
    for run_number in range(exp.get_run_count()):
        ''' setup levels of all factors for this run '''
        exp.set_run_number(run_number)
        run_definition = exp.get_run_identifier()
        c.execute("SELECT RunID FROM run_ids WHERE run_identifier=?",[run_definition])
        run_id = c.fetchone()[0]
        
        fact = exp.get_current_factor_level_by_id('fact_pairs')
        run_fact = exp.get_current_factor_level_by_id('fact_replication_id')
        all_nodes = exp.get_all_spec_nodes()
        for node in all_nodes:
            if node['real_id'] == exp.get_requester()["real_id"]:
                
                if (events_analysis == True):
                    print "using events deadline"
                    res=check_packets(run_id, node, deadline_events)
                elif (packets_analysis == True):
                    print "using packets deadline"
                    res=check_packets(run_id, node, deadline_packets)
                ''' checks for invalid runs and excludes the response times '''
                actornodes = [node]
                actornodes = actornodes + exp.get_responders()

                fails = check_routes(run_id, actornodes)
                
                if res==-1 or fails > 0:
                    fail = fail + 1
                else:
                    
                    if (events_analysis):
                    
                        index=valid_results['0'][fact]
                        delse = get_delay(run_id, node, services_needed)
                        delays_events.append(delse)
                        valid_results['0'][fact] = valid_results['0'][fact] + 1
                        if delse < deadline_events:
                            succeeded[0] = succeeded[0] + 1
                        else:
                            timedout[0] = timedout[0] + 1
                    if (packets_analysis):
                        for i,provider in enumerate(exp.get_responders()):
                            retry,delay = get_delay_packets(run_id, node, provider)
                            retries_packets.append(retry)
                            delays_packets.extend(delay)
                            
                            for d in delay:
                                valid_results['1'][fact] = valid_results['1'][fact] + 1
                                if d < deadline_packets:
                                    succeeded[1] = succeeded[1] + 1
                                else:
                                    timedout[1] = timedout[1] + 1
                                                   
                            if i == services_needed:
                                break
                break

        if events_analysis:
            sys.stdout.write("\rEvents-> Analyzed Runs: %d Valid: %d, Succeeded: %d, Timed out: %d, Failed: %d" % (run_number+1, valid_results['0'][0], succeeded[0], timedout[0], fail))
        if packets_analysis:
            sys.stdout.write("\rPackets-> Analyzed Runs: %d Valid: %d, Succeeded: %d, Timed out: %d, Failed: %d" % (run_number+1, valid_results['1'][0], succeeded[1], timedout[1], fail))
        sys.stdout.flush()
    
    sys.stdout.write("\n")
    
    for dist in dist_type:
        if (dist == 'cdf'):
            if (events_analysis):
                ecdf = sm.distributions.ECDF(delays_events)
                print_plot_cdf(fig_ecdf,ax_ecdf,ecdf.x,ecdf.y,1000,deadline_events)
            if (packets_analysis):
                pcdf = sm.distributions.ECDF(delays_packets)
                print_plot_cdf(fig_pcdf,ax_pcdf,pcdf.x,pcdf.y,1000,deadline_packets)
        else:
            if (events_analysis):
                weights = np.ones_like(np.array([float(value) for value in delays_events]))/len(delays_events)    
                print_plot_pdf(fig_epdf,ax_epdf,delays_events,50,weights,1000,deadline_events)
            if (packets_analysis):
                weights = np.ones_like(np.array([float(value) for value in delays_packets]))/len(delays_packets)    
                print_plot_pdf(fig_ppdf,ax_ppdf,delays_packets,50,weights,1000,deadline_packets)
    
    #plt.figure(2)
    #plt.subplot(212)
    #plt.plot(ecdf_retries.x, ecdf_retries.y, linestyle='-', drawstyle='steps', label=legend_string)
    #if run_number > 1500:
    #    plt.plot(ecdf_retries.x, ecdf_retries.y, linestyle='-', drawstyle='steps', label=legend_string)
    #else:
    #    plt.plot(ecdf_retries.x, ecdf_retries.y, linestyle='-.', drawstyle='steps', label=legend_string)
    #print_plot_packet_retries('cdf')
    #epdf_retries, bin_edges=np.histogram(retries, bins=6 , density=False)
    #epdf_retries_norm = np.array([float(value) for value in epdf_retries])/len(retries)

if __name__ == '__main__':
    
    global conn
    global cfg_search_fail_value
    global csv_file
    global deadline_events
    global deadline_packets
    global fn
    global fig_ecdf, fig_epdf
    global fig_pcdf, fig_ppdf
    global ax_ecdf, ax_epdf
    global ax_pcdf, ax_ppdf
    global data_num
    global figures
    global packets_analysis
    global events_analysis
    
    cfg_search_fail_value = -1000
    figures=[]

    # Option parser
    parser = argparse.ArgumentParser(
        description='Analyzer for done Service Discovery Experiments.',
        prog=os.path.basename(sys.argv[0]),
        version='%s 0.0.1' % os.path.basename(sys.argv[0]),
    )
    
    experiment_types = ['analyzer_single','analyzer_multi',
                        'get_responsiveness_single','get_responsiveness_multi',
                        'response_delays_single','response_delays_multi',
                        'get_timediffs_single','get_timediffs_multi',
                        'successful_query_delays_single',
                        'response_analysis']
    
    parser.add_argument('-l', type=int, dest='deadline_events', help='the deadline for the event based analysis')
    parser.add_argument('-lp', type=int, dest='deadline_packets', help='the deadline for the packets based analysis.')
    parser.add_argument('-d', dest='database', nargs='*', help='the database file')    
    parser.add_argument('-x', dest='exp_file', help='the abstract experiment description')
    parser.add_argument('-o', dest='csv_file', default="/tmp/results.csv", help='the file to which the results are written')
    parser.add_argument('-t', dest='analysis_type', help='type of analysis to perform on experiment data. Allowed values are: '+', '.join(experiment_types), metavar='', choices=experiment_types)
    parser.add_argument('-dt', dest='dist_type', nargs='*', help='type of distribution function.Allowed values are: '+', '.join(['pdf','cdf']), metavar='', choices=['pdf','cdf'])
    parser.add_argument('-p', dest='packets', help='analyze the packets of service discovery')
    parser.add_argument('-e', dest='events', help='analyze the events of service discovery')
    parser.add_argument('-m', dest='multi', default=False, help='analyze a multiple instances experiment')
    parser.add_argument('-r', type=int, dest='sdratio', help='percentage of service instances needed to be found', default = 100)
    
    options = parser.parse_args()
    
    if options.csv_file != None:
        csv_file = options.csv_file
    
    if options.database == None:
        print "Database file is needed"
        exit()
    
    if options.analysis_type == None:
        print "Analysis type is needed"
        exit()
    
    if (options.analysis_type == 'response_analysis') & (options.dist_type == None):
        print "Distribution type is needed for responsiveness analysis."
        exit()
            
    if options.events == None and options.packets == None:
        print "Must specify event and/or packet level of analysis"
        exit()
    else:
        events_analysis = options.events
        packets_analysis = options.packets
        if options.events == True and options.deadline_events == None:
            print "Events Deadline is needed"
            exit()
        else:
            deadline_events = options.deadline_events
            
        if options.packets == True and options.deadline_packets == None:
            print "Packets Deadline is needed"
            exit()
        else:
            deadline_packets = options.deadline_packets
 
    analysis = {'analyzer_single' : experiment_analyzer_single,
                'analyzer_multi' : experiment_analyzer_multi,
                'get_responsiveness_single' : get_responsiveness_single,
                'get_responsiveness_multi' : get_responsiveness_multi,
                'response_delays_single' : response_delays_single,
                'response_delays_multi' : response_delays_multi,
                'get_timediffs_single' : experiment_analyzer_single_get_timediffs,
                'get_timediffs_multi' : experiment_analyzer_multi_get_timediffs,
                'successful_query_delays_single' : successful_query_delays_single,
                'response_analysis' : response_analysis,
                }
    
    #fig, ax = plt.subplots()
    savename = "plots.pdf"
    pp= PdfPages(savename)
    
    fig_ecdf = plt.figure()
    ax_ecdf = fig_ecdf.add_subplot(1,1,1)
    fig_epdf = plt.figure()
    ax_epdf = fig_epdf.add_subplot(1,1,1)
    
    fig_pcdf = plt.figure()
    ax_pcdf = fig_pcdf.add_subplot(1,1,1)
    fig_ppdf = plt.figure()
    ax_ppdf = fig_ppdf.add_subplot(1,1,1)
    
    for data_num,database in enumerate(options.database):
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
            
        analysis[options.analysis_type](options.sdratio,options.dist_type)
        #experiment_analyzer(options.sdratio)
        
    for fig in figures:
        pp.savefig(fig, dpi=600)
    pp.close()
