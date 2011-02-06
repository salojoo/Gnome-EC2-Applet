#!/usr/bin/env python
import pygtk
import sys
pygtk.require('2.0')

import gtk
import gnomeapplet

import boto.ec2


class AmazonEC2Controller:
    STATE_RUNNING = 0
    STATE_TO_RUNNING = 1
    STATE_SHUTDOWN = 2
    STATE_TO_SHUTDOWN = 3
    STATE_UNKNOWN = 4
    
    
    def replace_icon(self, state):
        self.applet.remove( self.icon )
        
        if state == self.STATE_RUNNING:
            self.icon = self.icon_running
        if state == self.STATE_TO_RUNNING:
            self.icon = self.icon_to_running
        if state == self.STATE_SHUTDOWN:
            self.icon = self.icon_shutdown
        if state == self.STATE_TO_SHUTDOWN:
            self.icon = self.icon_to_shutdown
        if state == self.STATE_UNKNOWN:
            self.icon = self.icon_unknown

        self.applet.add( self.icon )
        self.applet.show_all()
        
        
    
    def menu_start(self, *arguments):
        self.replace_icon(self.STATE_TO_RUNNING)
        self.state = self.STATE_TO_RUNNING
        print "menu start"
    
    def menu_shutdown(self, *arguments):
        self.replace_icon(self.STATE_TO_SHUTDOWN)
        self.state = self.STATE_TO_SHUTDOWN
        print "menu shutdown"
    
    def menu_configuration(self, *arguments):
        print "menu configure"
        
    
    
    def __init__(self, applet, iid):
        print "Initializing the applet"
        self.applet = applet
        self.icon_unknown = gtk.Image()
        self.icon_unknown.set_from_file("icon_unknown.png")
        self.icon_running = gtk.Image()
        self.icon_running.set_from_file("icon_running.png")
        self.icon_shutdown = gtk.Image()
        self.icon_shutdown.set_from_file("icon_shutdown.png")
        self.icon_to_running = gtk.Image()
        self.icon_to_running.set_from_file("icon_to_running.png")
        self.icon_to_shutdown = gtk.Image()
        self.icon_to_shutdown.set_from_file("icon_to_shutdown.png")
        
        self.state = self.STATE_UNKNOWN # set directly only this one time in initialization
        self.icon = self.icon_unknown
        self.replace_icon(self.STATE_UNKNOWN)
        
        
        
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
