'''
This module implements an XMLRPC server to asynchonously receive
messages (events) from the experiment nodes.

It features a Queue and a mechanism to interact with the ExperiMaster

'''
from SimpleXMLRPCServer import SimpleXMLRPCServer
from SimpleXMLRPCServer import SimpleXMLRPCRequestHandler
import xmlrpclib
import thread
import os
import sys
import threading
from datetime import datetime

# Restrict to a particular path.
class RequestHandler(SimpleXMLRPCRequestHandler):
    rpc_paths = ('/RPC2',)
    

class eventsRPC:
    _wait_for_type = ""
    _event_was_type= ""
    
    def __init__(self, event_condition, event_log, verbose):
        self._event_condition = event_condition
        self._event_log = event_log
        self.verbose = verbose
    
    def _inject_event(self, node, timestamp, type, param):
        self.event(node,timestamp,type,param)
    
    def _clear(self):
        self._event_condition.acquire()
        for i in range(len(self._event_log)):
            self._event_log.pop()
        self._event_condition.release()
        
    def event(self, node, timestamp, type, param):
        '''
        This function is called by the RPC clients.
        It puts the received event into a list and
        notifies waiting threads that an event has
        occurred.
        '''
        if self.verbose:
            print "EH: got event %s at %s from %s " % (type,timestamp,node)
        self._event_condition.acquire()
        try:
            self._event_log.append( ( datetime.now(), node, timestamp, type, param ) )
        except:
            print "EH:ERROR"
        self._event_condition.notifyAll()
        self._event_condition.release()
            
        return 0
    
class StoppableRPCServer(SimpleXMLRPCServer):

    stopped = False
    allow_reuse_address = True

    def __init__(self, *args, **kw):
        SimpleXMLRPCServer.__init__(self, *args, **kw)
        self.register_function(lambda: 'OK', 'ping')
        self.is_finally_done = 0
        
    def serve_forever(self):
        while not self.stopped:
            try:
                self.handle_request()
            except Exception, e:
                print "Exception: ",e

        print "EH: Done"
        self.is_finally_done = 1

    def force_stop(self):
        self.stopped = True
        if self.is_finally_done==0:
            self.create_dummy_request()
        self.server_close()
        #self.create_dummy_request()


    def create_dummy_request(self):
        server = xmlrpclib.Server('http://localhost:8000')
        try:
            server.ping()
        except:
            pass
        
class EventHandler:

    def __init__(self,verbose):
        print "EH: Init"
        self.verbose = verbose
        self.event_log = []
        self.event_condition = threading.Condition()
        self.events = eventsRPC(self.event_condition, self.event_log,verbose)
    
    def __del__(self):
        pass    
        
    def inject_event(self, node, timestamp, type, param):
        print "EH: injecting event %s" %(type)
        self.events._inject_event(node, timestamp, type, param)
        print "EH: injection of event done"
        
    def event_thread(self):
        print "EH: Start"
        self.server = StoppableRPCServer(('', 8000),logRequests=False, requestHandler=RequestHandler)
        self.server.register_introspection_functions()
        self.server.register_instance( self.events )
        # Run the server's main loop
        if self.verbose:
            print "EH: Main loop running"
        try:
            self.server.serve_forever()
            print "EH: Stopped serving"
        except (KeyboardInterrupt, SystemExit):
            print "Program was terminated by CTRL+C"

    def clear_log(self):
        self.events._clear()

    def start_event_handler(self):
        # Create server 
        #'' means bind to all addresses
        thread.start_new_thread(self.event_thread, ())
        
        
    def stop_event_handler(self):
        self.server.force_stop()