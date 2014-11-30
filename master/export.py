from exp_description import *
import sqlite3
import os

def init_db():
    global conn 
    c = conn.cursor()

    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='measurements'")
    if c.fetchone()==None:
        # Create table
        c.execute('''CREATE TABLE "measurements" (
        "runID" TEXT,
        "nodeID" TEXT,
        "eventList" TEXT,
        "packets" BLOB,
        "timeDiff" INTEGER,
        "topo" TEXT)''')
        
        # Save (commit) the changes
        conn.commit()
        # We can also close the cursor if we are done with it
        c.close()

def run_dir_exporter(exp_dir, run_id, node, c):
    init_db()
    c.execute("SELECT * FROM measurements WHERE runID=? ", [run_id] )
    for measurement in c:
        if measurement[1]!=node['real_id']:
            continue
        #get events
        fd = open("%s/nodes/%s/event_log_%s.log" % (exp_dir,run_id, node['real_id']),"w")
        fd.write(measurement[2])
        fd.close()
        pass
    
        time_diff = 0
        #get time diff info
        if node['abstract_id']!="" and measurement[4]!=None:  
            fd = open("%s/master/%s/ping_t_%s" % (exp_dir,run_id, node['real_id']),"w")
            fd.write(str(measurement[4]))        
            fd.close()
            pass
            
        # get routes infor
        
        # copy packets
        if node['abstract_id']!="":        
            cap = "%s/nodes/%s/capture/%s.pcap" %(exp_dir, run_id,node['real_id'])
            #print measurement[3]
            with open(cap, "wb") as output_file: 
                output_file.write(measurement[3]) 
   
    


    
def experiment_dir_exporter(exp_dir):
    global csv_file
    global exp
    global conn
    
    c = conn.cursor()
    #loop over run sequence
    for run_number in range(exp.get_run_count()):
        ###### SETUP LEVELS OF ALL FACTORS FOR THIS RUN ########
        exp.set_run_number(run_number)
        run_definition = exp.get_run_identifier()
        print "exporting run number %d with combination %s" %(run_number,run_definition)
  
        # import measurements from nodes and master
        # event lists, packets, topo, timediff

        if os.path.exists("%s/%s"%(exp_dir,run_definition))==False:
            try:
                if os.path.exists("%s/master/%s/ping_t"%(exp_dir,run_definition))==False:
                    os.makedirs("%s/master/%s/ping_t"%(exp_dir,run_definition))
                if os.path.exists("%s/nodes/%s/capture"%(exp_dir,run_definition))==False:
                    os.makedirs("%s/nodes/%s/capture"%(exp_dir,run_definition))
                if os.path.exists("%s/nodes/%s/capture"%(exp_dir,run_definition))==False:
                    os.makedirs("%s/nodes/%s/capture"%(exp_dir,run_definition))
            except:
                print "Directory creation error"
                break
        all_nodes = exp.get_all_spec_nodes()
        for node in all_nodes:
            run_dir_exporter(exp_dir,run_definition,node,c)
    conn.commit()
    
if __name__ == '__main__':
    global exp
    global conn
    
    
    
    parser = optparse.OptionParser(
        description='Import Service Discovery Experiments.',
        prog=os.path.basename(sys.argv[0]),
        version='%s 0.0.1' % os.path.basename(sys.argv[0]),
    )
    parser.add_option('-e', metavar='experiment_dir', dest='experiment_dir', help='Name of the target experiment dir')
    parser.add_option('-x', metavar='exp_file', dest='exp_file', help='the abstract experiment description')
    parser.add_option('-d', metavar='database', dest='database', help='the sqlite file to be exported')
    parser.add_option('-o', metavar='csv_file', dest='csv_file', help='the file to which the results are written')
    
    options, arguments = parser.parse_args()
    
    if options.experiment_dir==None:
        print "Need experiment dir"
        exit()
    
    if options.database == None:
        print "Database file is needed"
        exit()
        
    conn = sqlite3.connect(options.database)
    exp = experiment_description(options.exp_file)
    #exp.summary()
    experiment_dir_exporter(options.experiment_dir)
    
   
