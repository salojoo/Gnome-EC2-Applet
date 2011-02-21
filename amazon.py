#!/usr/bin/env python
import pygtk
import sys
pygtk.require('2.0')

import gtk
import gnomeapplet
from httplib import HTTPConnection
from urllib import urlencode, quote
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
        self.replace_icon("unknown", "Initializing")
        
        # list of instance names or id's for tooltip
        self.names = ""
        
        # init conifg
        self.read_gconf()
        
        # timeout for ec2 queries
        self.timeout = 5
        
        # this flag is set then instances are started
        # when they reach started state the elastic ips are set
        self.ip_pending = False
        
        
        # create right-click-menu
        menu = open(STUFF_ROOT_DIR + "/menu.xml").read()
        verbs = [("Start", self.menu_start), ("Shutdown", self.menu_shutdown), 
                 ("Configuration", self.menu_configuration), ("Refresh", self.menu_refresh)]
        applet.setup_menu(menu, verbs, None)
        applet.set_background_widget(applet) # /* enable transparency hack */
        
        # update now and in future
        self.fast_poll_baseline = time.time()
        self.fast_poll_timeout = 10 * 1000 #10sec
        self.slow_poll_timeout = 300 * 1000 #5mins
        self.fast_poll_timeframe = 180 #3mins of fast polling after any user action or state change
        self.current_poll_timeout = self.fast_poll_timeout
        self.update()
        gtk.timeout_add(self.current_poll_timeout, self.update, self)
        
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
            self.replace_icon( "unknown", "Connection Problem!\n" +  self.names )
            return False
        
        if response.status != 200:
            print "Status: " + str( response.status )
            print response.read()
            return False
        
        # return xml
        return minidom.parseString( response.read() )
        
        
        
    
    def replace_icon(self, state, tooltip = None):
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
        
        if tooltip:
            self.icon.set_tooltip_text(tooltip)
        self.applet.add( self.icon )
        self.applet.show_all()
        
        
    # TODO connect and menu.xml
    def menu_refresh(self, *arguments):
        self.fast_poll_baseline = time.time()
        self.update()
        
    def menu_start(self, *arguments):
        self.fast_poll_baseline = time.time()
        self.replace_icon("pending", self.names)
        self.state = "pending"
        
        
        
        # start instances
        params = {}
        i = 1
        for inst in self.instances:
            params["InstanceId." + str(i)] = inst
            i += 1
        self.ec2_query("StartInstances", params )
        
        self.ip_pending = True
        
        
            
    
    def menu_shutdown(self, *arguments):
        self.fast_poll_baseline = time.time()
        self.replace_icon("stopping", self.names)
        self.state = "stopping"
        
        params = {}
        i = 1
        for inst in self.instances:
            params["InstanceId." + str(i)] = inst
            i += 1
        
        self.ec2_query("StopInstances", params )
            
    
    # callback function for handling save and cancel events
    # from configuration window
    def menu_callback(self, widget, data):
        self.fast_poll_baseline = time.time()
        
        if data == "cancel":
            self.window.destroy()
            
        elif data == "save":
            # get values from the entryboxes to local variables
            # and save from that to gconf
            # TODO input validation
            access_key = self.entry_access_key.get_text()
            secret_key = self.entry_secret_key.get_text()
            region_address = self.entry_region_address.get_text()
            instances = self.entry_instances.get_text()
            
            # write/read cycle with gconf also sets the local variables of this applet class
            self.write_gconf(access_key, secret_key, region_address, instances)
            self.read_gconf()
            
            self.window.destroy()
    
    # configuration window
    # some of the elements are related to self
    # because they are used in the callback function
    def menu_configuration(self, *arguments):
        self.fast_poll_baseline = time.time()
        
        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.set_title("Amazon EC2 Controller")
        self.window.set_border_width(10)

        # fixed layout container
        fixed = gtk.Fixed()
        self.window.add( fixed )
        
        # access key
        label_access_key = gtk.Label("Access key:")
        label_access_key.show()
        fixed.put( label_access_key, 0, 5 )
        self.entry_access_key = gtk.Entry()
        self.entry_access_key.set_text( self.access_key )
        self.entry_access_key.set_width_chars(80)
        self.entry_access_key.show()
        fixed.put( self.entry_access_key, 130, 0 )
        
        # secret key
        label_secret_key = gtk.Label("Secret key:")
        label_secret_key.show()
        fixed.put( label_secret_key, 0, 35 )
        self.entry_secret_key = gtk.Entry()
        self.entry_secret_key.set_text( self.secret_key )
        self.entry_secret_key.set_width_chars(80)
        self.entry_secret_key.show()
        fixed.put( self.entry_secret_key, 130, 30 )
        
        # instances
        label_instances = gtk.Label("Instances:")
        label_instances.show()
        fixed.put( label_instances, 0, 65 )
        self.entry_instances = gtk.Entry()
        self.entry_instances.set_text( ",".join(self.instances) )
        self.entry_instances.set_width_chars(80)
        self.entry_instances.show()
        fixed.put( self.entry_instances, 130, 60 )
        label_instances_info = gtk.Label()
        label_instances_info.set_markup("<i>Comma separated list of instances with optional ip: i-xxxxxxxx (elastic-ip)</i>")
        label_instances_info.show()
        fixed.put( label_instances_info, 130, 90 )
        
        # region addresses
        label_region_address = gtk.Label("Region address:")
        label_region_address.show()
        fixed.put( label_region_address, 0, 125 )
        self.entry_region_address = gtk.Entry()
        self.entry_region_address.set_text( self.region_address )
        self.entry_region_address.set_width_chars(80)
        self.entry_region_address.show()
        fixed.put( self.entry_region_address, 130, 120 )
        label_region_info = gtk.Label()
        label_region_info.set_markup("""<i>ec2.us-east-1.amazonaws.com
ec2.us-west-1.amazonaws.com
ec2.eu-west-1.amazonaws.com
ec2.ap-southeast-1.amazonaws.com</i>""")
        label_region_info.show()
        fixed.put( label_region_info, 130, 150 )
        
        
        
        # save and cancel buttons
        button_cancel = gtk.Button("cancel")
        button_cancel.show()
        button_cancel.connect("clicked", self.menu_callback, "cancel")
        fixed.put(button_cancel, 0, 240)
        button_save = gtk.Button("save")
        button_save.connect("clicked", self.menu_callback, "save")
        button_save.show()
        fixed.put(button_save, 130, 240)
        
        
        # show everything
        fixed.show()
        self.window.show()
        
    
    def update(self, event = None):
    
        try:
            params = {}
            i = 1
            for inst in self.instances:
                key = "InstanceId." + str(i)
                params[key] = inst
                i += 1
            
            xml = self.ec2_query("DescribeInstances", params )
            if not xml: raise Exception("ec2_query error")


            # generate namelist to use as tooltip
            self.names = ""
            
            
            # the instances are first grouped by reservation id and then instances id
            # many instances may be in one reservation group
            states = []
            
            for inst_set in xml.getElementsByTagName("instancesSet"):
                for inst in inst_set.getElementsByTagName("item"):
                    # width-first search of items that are direct children of the instanceset
                    if inst.parentNode != inst_set: continue
                    
                    inst_id = ""
                    inst_name = ""
                    
                    inst_id = inst.getElementsByTagName("instanceId")[0].firstChild.wholeText
                    states += [inst.getElementsByTagName("name")[0].firstChild.wholeText]
                    tagset = inst.getElementsByTagName("tagSet")
                    
                    # get name of instance, if given in tags
                    inst_name = None
                    if len(tagset) != 0:
                        for tag in tagset[0].getElementsByTagName("item"):
                            key = tag.getElementsByTagName("key")[0].firstChild.wholeText
                            value = tag.getElementsByTagName("value")[0].firstChild.wholeText
                            if key == "Name": 
                                inst_name = value
                                break
                        
                    # add name to if it is defined in tags otherwise add the id
                    # add state of the instance in parantheses
                    if self.names:
                        self.names = self.names + "\n"
                    if inst_name:
                        self.names = self.names + inst_name + " (" + states[-1:][0] + ")"
                    else:
                        self.names = self.names + inst_id + " (" + states[-1:][0] + ")"
            
            # state is the state of the first machine
            if self.state != states[0]:
                self.fast_poll_baseline = time.time()
            
            self.state = states[0]
            
            
            if self.ip_pending:
                all_running = True
                for state in states:
                    if state != "running":
                        all_running = False

                # associate ip addresses now that the instances all came to running state
                if all_running:
                    for inst, ip in self.ip.iteritems():
                        params = {"PublicIp": ip,
                                  "InstanceId": inst}
                        self.ec2_query("AssociateAddress", params)
                    self.ip_pending = False
            
            self.replace_icon( self.state, self.names )
        
        
        except: # continue the timeout loop no-matter-what
            try:
                # try to also print the message 
                print "Update exception:", sys.exc_info()[0], sys.exc_info()[1]
            except:
                print "Update exception:", sys.exc_info()[0]
            
            # set unknown state and reset fast poll baseline to activate fast-polling
            self.fast_poll_baseline = time.time()
            self.state = "unknown"
            tooltip = "Last known state: \n" + self.names
            self.replace_icon( self.state, tooltip )
        
        # continue or reset the timer
        # the timer has two modes: slow-poll and fast-poll
        
        if time.time() > self.fast_poll_baseline + self.fast_poll_timeframe:
            # should use slow-poll timeout
            
            if self.current_poll_timeout == self.slow_poll_timeout:
                return 1
            elif self.current_poll_timeout == self.fast_poll_timeout:
                # change to slow-poll timeout
                print "switching to slow-poll mode"
                self.current_poll_timeout = self.slow_poll_timeout
                gtk.timeout_add(self.current_poll_timeout, self.update, self)
                return 0
                
        
        else:    # should use fast-poll timeout
            if self.current_poll_timeout == self.slow_poll_timeout:
                print "switching to fast-poll mode"
                self.current_poll_timeout = self.fast_poll_timeout
                gtk.timeout_add(self.current_poll_timeout, self.update, self)
                return 0
            elif self.current_poll_timeout == self.fast_poll_timeout:
                return 1
            
        
    def read_gconf(self):
        client = gconf.client_get_default()
        gconf_root_key = self.applet.get_preferences_key()
        self.access_key = client.get_string( gconf_root_key + "/access_key") or ""
        self.secret_key = client.get_string( gconf_root_key + "/secret_key") or "" 
        self.region_address = client.get_string( gconf_root_key + "/region_address") or ""
        
        self.instances = []
        self.ip = {} # ip[instance] = ip
        for inst in (client.get_string( gconf_root_key + "/instances") or "").split(","):
            inst = inst.strip()
            ip_begin = inst.find("(")
            ip_end = inst.find(")")
            if ip_begin > 0 and ip_end > 0:
                self.ip[inst[:ip_begin]] = inst[ip_begin+1:ip_end]
                self.instances += [inst[:ip_begin]]
            else:
                self.instances += [inst]
        
    def write_gconf(self, access_key, secret_key, region_address, instances):
        client = gconf.client_get_default()
        gconf_root_key = self.applet.get_preferences_key()
        client.set_string( gconf_root_key + "/access_key", access_key)
        client.set_string( gconf_root_key + "/secret_key", secret_key)
        client.set_string( gconf_root_key + "/region_address", region_address)
        client.set_string( gconf_root_key + "/instances", instances)
    
    
    


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
    
    
