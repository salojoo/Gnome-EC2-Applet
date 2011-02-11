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
import socket
import gconf


STUFF_ROOT_DIR = "/usr/share/gnome-applets/ec2-controller"

class AmazonEC2Controller:

    def __init__(self, applet, iid):
        print "Initializing the applet"
        
        # this is referenced many times afterwards
        self.applet = applet
        
        # load icons
        self.icon_unknown = gtk.Image()
        self.icon_unknown.set_from_file( STUFF_ROOT_DIR + "/icon_unknown.png")
        self.icon_running = gtk.Image()
        self.icon_running.set_from_file( STUFF_ROOT_DIR + "/icon_running.png")
        self.icon_stopped = gtk.Image()
        self.icon_stopped.set_from_file( STUFF_ROOT_DIR + "/icon_stopped.png")
        self.icon_pending = gtk.Image()
        self.icon_pending.set_from_file( STUFF_ROOT_DIR + "/icon_pending.png")
        self.icon_stopping = gtk.Image()
        self.icon_stopping.set_from_file( STUFF_ROOT_DIR + "/icon_stopping.png")
        
        # initial state and view
        self.state = "unknown" # set directly only this one time in initialization
        self.icon = self.icon_unknown
        self.replace_icon("unknown")

        # init conifg
        self.read_gconf()
        
        # timeout for ec2 queries
        self.timeout = 5
        
        
        # create right-click-menu
        menu = open(STUFF_ROOT_DIR + "/menu.xml").read()
        verbs = [("Start", self.menu_start), ("Shutdown", self.menu_shutdown), ("Configuration", self.menu_configuration)]
        applet.setup_menu(menu, verbs, None)
        applet.set_background_widget(applet) # /* enable transparency hack */
        
        # update now and in future
        self.update()
        self.update_interval = 10 * 1000
        gtk.timeout_add(self.update_interval, self.update, self)
        
        self.applet.show_all()

    def ec2_query( self, action, params = {}):
        if not self.access_key or not self.secret_key or not self.region_address:
            return False
        
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        params["Action"] = action
        params["Version"] = "2010-11-15"
        params["Timestamp"] = timestamp
        params["SignatureVersion"] = "2"
        params["SignatureMethod"] = "HmacSHA256"
        params["AWSAccessKeyId"] = self.access_key
        
        
        signature = hmac.new( key = self.secret_key, digestmod = hashlib.sha256 )
        signature.update( "GET" + "\n" )
        signature.update( self.region_address.lower() + "\n" )
        signature.update( "/\n" )
        
        sep = False
        for i in sorted( params ):
            if sep: signature.update("&")
            else:   sep = True
            signature.update(quote( i ) + "=" + quote( params[i] ))
        params["Signature"] = b64encode( signature.digest() )
        
        # connection
        try:
            socket.setdefaulttimeout(self.timeout)
            http = HTTPConnection( self.region_address )
            http.request("GET", "/?" + urlencode(params))
            response = http.getresponse()
        except:
            print "Connection problem"
            self.replace_icon( "unknown" )
            return False
        
        if response.status != 200:
            print "Status: " + str( response.status )
            print response.read()
            return False
        
        # return xml
        return minidom.parseString( response.read() )
        
        
        
    
    def replace_icon(self, state):
        self.applet.remove( self.icon )
        
        if state == "running":
            self.icon = self.icon_running
        elif state == "pending":
            self.icon = self.icon_pending
        elif state == "stopped":
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
            
    
    # callback function for handling save and cancel events
    # from configuration window
    def menu_callback(self, widget, data):
        if data == "cancel":
            self.window.destroy()
            
        elif data == "save":
            # get values from the entryboxes to local variables
            # and save from that to gconf
            self.access_key = self.entry_access_key.get_text()
            self.secret_key = self.entry_secret_key.get_text()
            self.region_address = self.entry_region_address.get_text()
            self.reservation_id = self.entry_reservation_id.get_text()
            self.write_gconf()
            
            self.window.destroy()
    
    # configuration window
    # some of the elements are related to self
    # because they are used in the callback function
    def menu_configuration(self, *arguments):
        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.set_title("Amazon EC2 Controller")
        self.window.set_border_width(10)

        # fixed layout container
        fixed = gtk.Fixed()
        self.window.add( fixed )
        
        # access key
        label_access_key = gtk.Label("Access key:")
        label_access_key.show()
        fixed.put( label_access_key, 0, 0 )
        self.entry_access_key = gtk.Entry()
        self.entry_access_key.set_text( self.access_key )
        self.entry_access_key.set_width_chars(50)
        self.entry_access_key.show()
        fixed.put( self.entry_access_key, 150, 0 )
        
        # secret key
        label_secret_key = gtk.Label("Secret key:")
        label_secret_key.show()
        fixed.put( label_secret_key, 0, 30 )
        self.entry_secret_key = gtk.Entry()
        self.entry_secret_key.set_text( self.secret_key )
        self.entry_secret_key.set_width_chars(50)
        self.entry_secret_key.show()
        fixed.put( self.entry_secret_key, 150, 30 )
        
        # reservation id
        label_reservation_id = gtk.Label("Reservation id:")
        label_reservation_id.show()
        fixed.put( label_reservation_id, 0, 60 )
        self.entry_reservation_id = gtk.Entry()
        self.entry_reservation_id.set_text( self.reservation_id )
        self.entry_reservation_id.set_width_chars(50)
        self.entry_reservation_id.show()
        fixed.put( self.entry_reservation_id, 150, 60 )
        
        # region addresses
        label_region_address = gtk.Label("Region address:")
        label_region_address.show()
        fixed.put( label_region_address, 0, 90 )
        self.entry_region_address = gtk.Entry()
        self.entry_region_address.set_text( self.region_address )
        self.entry_region_address.set_width_chars(50)
        self.entry_region_address.show()
        fixed.put( self.entry_region_address, 150, 90 )
        
        
        
        # save and cancel buttons
        button_cancel = gtk.Button("cancel")
        button_cancel.show()
        button_cancel.connect("clicked", self.menu_callback, "cancel")
        fixed.put(button_cancel, 0, 120)
        button_save = gtk.Button("save")
        button_save.connect("clicked", self.menu_callback, "save")
        button_save.show()
        fixed.put(button_save, 150, 120)
        
        
        # show everything
        fixed.show()
        self.window.show()
    
    
    def get_instances(self):
        params = {  "Filter.1.Name":"reservation-id",
                    "Filter.1.Value.1":self.reservation_id }
        
        xml = self.ec2_query("DescribeInstances", params )
        if not xml: return []
        
        instances = []
        for inst in xml.getElementsByTagName("instanceId"):
            instances += [inst.firstChild.wholeText]
        
        return instances
        
        
    
    def update(self, event = None):
        params = {  "Filter.1.Name":"reservation-id",
                    "Filter.1.Value.1":self.reservation_id}
        
        xml = self.ec2_query("DescribeInstances", params )
        if not xml: return 1

        # get the status of the first instance in the reservation set
        instance = xml.getElementsByTagName("instanceState")[0]
        self.state = instance.getElementsByTagName("name")[0].firstChild.wholeText
        
        print "Instance state: " + self.state
        self.replace_icon( self.state )
        
        # continue the timer
        return 1
        
    def read_gconf(self):
        client = gconf.client_get_default()
        gconf_root_key = self.applet.get_preferences_key()
        print "gconf key: " + gconf_root_key
        self.access_key = client.get_string( gconf_root_key + "/access_key") or ""
        self.secret_key = client.get_string( gconf_root_key + "/secret_key") or "" 
        self.region_address = client.get_string( gconf_root_key + "/region_address") or ""
        self.reservation_id = client.get_string( gconf_root_key + "/reservation_id") or ""
        
    def write_gconf(self):
        client = gconf.client_get_default()
        gconf_root_key = self.applet.get_preferences_key()
        client.set_string( gconf_root_key + "/access_key", self.access_key)
        client.set_string( gconf_root_key + "/secret_key", self.secret_key)
        client.set_string( gconf_root_key + "/region_address", self.region_address)
        client.set_string( gconf_root_key + "/reservation_id", self.reservation_id)
    
    
    


def sample_factory(applet, iid):
    AmazonEC2Controller(applet, iid)
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
    ret = gnomeapplet.bonobo_factory("OAFIID:GNOME_AmazonAWSApplet_Factory", 
                             gnomeapplet.Applet.__gtype__, 
                             "hello", "0", sample_factory)
    
    
