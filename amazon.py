#!/usr/bin/env python
import pygtk
import sys
pygtk.require('2.0')

import gtk
import gnomeapplet
from httplib import HTTPConnection
from urllib import urlencode, quote
import config
import hmac, hashlib
from base64 import b64encode
import time
from xml.dom import minidom




class AmazonEC2Controller:
    

    def ec2_query( self, action, params = {}):
        http = HTTPConnection( self.REGION, timeout = self.timeout )
        
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        params["Action"] = action
        params["Version"] = "2010-11-15"
        params["Timestamp"] = timestamp
        params["SignatureVersion"] = "2"
        params["SignatureMethod"] = "HmacSHA256"
        params["AWSAccessKeyId"] = self.AWS_ACCESS_KEY_ID
        
        
        signature = hmac.new( key = self.AWS_SECRET_ACCESS_KEY, digestmod = hashlib.sha256 )
        signature.update( "GET" + "\n" )
        signature.update( self.REGION.lower() + "\n" )
        signature.update( "/\n" )
        
        sep = False
        for i in sorted( params ):
            if sep: signature.update("&")
            else:   sep = True
            signature.update(quote( i ) + "=" + quote( params[i] ))
        params["Signature"] = b64encode( signature.digest() )

        http.request("GET", "/?" + urlencode(params))
        response = http.getresponse()
        
        if response.status != 200:
            print "Status: " + str( response.status )
            print response.read()
            return 0
        
        # return xml
        return minidom.parseString( response.read() )
        
        
        
    
    def replace_icon(self, state):
        self.applet.remove( self.icon )
        
        if state == "running":
            self.icon = self.icon_running
        elif state == "pending":
            self.icon = self.icon_pending
        elif state == "stopped":
            print "setting stopped icon"
            self.icon = self.icon_stopped
        elif state == "stopping":
            self.icon = self.icon_stopping
        else:
            self.icon = self.icon_unknown

        self.applet.add( self.icon )
        self.applet.show_all()
        
        
    
    def menu_start(self, *arguments):
        self.replace_icon("pending")
        self.state = "pending"
        
        for inst in self.get_instances():
            self.ec2_query("StartInstances", {"InstanceId.1": inst} )
        
        
        
    
    def menu_shutdown(self, *arguments):
        self.replace_icon("stopping")
        self.state = "stopping"
        
        for inst in self.get_instances():
            self.ec2_query("StopInstances", {"InstanceId.1": inst} )
        
    
    def menu_configuration(self, *arguments):
        print "TODO: implement configuration"
    
    
    def get_instances(self):
        params = {  "Filter.1.Name":"reservation-id",
                    "Filter.1.Value.1":config.RESERVATION_ID}
        xml = self.ec2_query("DescribeInstances", params )
        
        instances = []
        for inst in xml.getElementsByTagName("instanceId"):
            instances += [inst.firstChild.wholeText]
        
        return instances
        
        
    
    def update(self, event = None):
        params = {  "Filter.1.Name":"reservation-id",
                    "Filter.1.Value.1":config.RESERVATION_ID}
        xml = self.ec2_query("DescribeInstances", params )

        # get the status of the first instance in the reservation set
        instance = xml.getElementsByTagName("instanceState")[0]
        self.state = instance.getElementsByTagName("name")[0].firstChild.wholeText
        
        print "Instance state: " + self.state
        self.replace_icon( self.state )
        
        # continue the timer
        return 1
    
    def __init__(self, applet, iid):
        print "Initializing the applet"
        self.applet = applet
        self.icon_unknown = gtk.Image()
        self.icon_unknown.set_from_file("icon_unknown.png")
        self.icon_running = gtk.Image()
        self.icon_running.set_from_file("icon_running.png")
        self.icon_stopped = gtk.Image()
        self.icon_stopped.set_from_file("icon_stopped.png")
        self.icon_pending = gtk.Image()
        self.icon_pending.set_from_file("icon_pending.png")
        self.icon_stopping = gtk.Image()
        self.icon_stopping.set_from_file("icon_stopping.png")
        
        self.state = "unknown" # set directly only this one time in initialization
        self.icon = self.icon_unknown
        self.replace_icon("unknown")
        
        
        
        # settings for EC2 queries
        self.AWS_ACCESS_KEY_ID = config.AWS_ACCESS_KEY_ID
        self.AWS_SECRET_ACCESS_KEY = config.AWS_SECRET_ACCESS_KEY
        self.REGION = config.REGION
        self.timeout = 5
        
        
        # update now and in future
        self.update()
        self.update_interval = 10 * 1000
        gtk.timeout_add(self.update_interval,self.update, self)
        
        menu = open("menu.xml").read()
        verbs = [("Start", self.menu_start), ("Shutdown", self.menu_shutdown), ("Configuration", self.menu_configuration)]
        applet.setup_menu(menu, verbs, None)
        applet.set_background_widget(applet) # /* enable transparency hack */
        
        self.applet.show_all()


def sample_factory(applet, iid):
    print "sample_factory()"
    AmazonEC2Controller(applet, iid)
    print "factory exiting"
    return True
    

if len(sys.argv) == 2 and sys.argv[1] == "run-in-window":   
    main_window = gtk.Window(gtk.WINDOW_TOPLEVEL)
    main_window.set_title("Python Applet")
    main_window.connect("destroy", gtk.mainquit) 
    app = gnomeapplet.Applet()
    sample_factory(app, None)
    app.reparent(main_window)
    main_window.show_all()
    gtk.main()
    sys.exit()

if __name__ == '__main__':
    print "starting factory"
    ret = gnomeapplet.bonobo_factory("OAFIID:GNOME_AmazonAWSApplet_Factory", 
                             gnomeapplet.Applet.__gtype__, 
                             "hello", "0", sample_factory)
    print "done " + str(ret)
