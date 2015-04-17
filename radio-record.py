# -*- coding: utf8 -*-
# radio-record v0.1 (July 2015)
#
# Copyright (C) 2015 Jurassicplayer <jurassicplayer.github.io>
# Rhythmbox 2.96 and higher compatible
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301  USA.

from gi.repository import GObject, Gtk, Pango, Peas, RB, Gio, Gdk
import subprocess, os, time, threading, _thread, configparser, shutil, re, codecs, urllib

class radioRecord (GObject.Object, Peas.Activatable):
    object = GObject.property (type = GObject.Object)
    
    def __init__(self):
        GObject.Object.__init__(self)
    
    def refresh_ui(self):
        try:
            shell = self.object
            page = shell.props.selected_page
            if not hasattr(page, 'get_entry_view'):
                print('No entry view')
                return
            selected = page.get_entry_view().get_selected_entries()
            ## If selected has an entry
            if selected != []:
                ## If that entry isn't the same as the previous
                current_uri = selected[0].get_playback_uri()
                if current_uri != self.uri:
                    self.uri = current_uri
                    try:
                        ## If the entry has a recording going
                        if self.runningDB[str(current_uri)] == 'running':
                            print('Recording')
                            self.create_stop('swap-entry')
                        ## Else if the entry doesn't
                        else:
                            print('Not recording')
                            self.create_record('swap-entry')
                            self.runningDB.update({str(current_uri):'stopped'})
                    except KeyError:
                        print('Not recording')
                        self.create_record('swap-entry')
                        self.runningDB.update({str(current_uri):'stopped'})
                
        except Exception as e:
            print(e)
            pass
        return True
    
    
    def do_activate(self):
        self.uri = ""
        self.status = ""
        self.runningDB = {}

        GObject.timeout_add(GObject.PRIORITY_DEFAULT_IDLE, self.refresh_ui)
        ##Gdk.threads_add_idle(GObject.PRIORITY_DEFAULT_IDLE, self.refresh_ui))
        
        
    ## Create the recording button after stopping current recording.
    def create_record(self, action, *args):
        
        app = Gio.Application.get_default()
        app.remove_plugin_menu_item('iradio-toolbar', self.status)
        self.status = 'record-radio'
        app = Gio.Application.get_default()
        action = Gio.SimpleAction(name=self.status)
        action.connect('activate', self.record_radio)
        app.add_action(action)
        
        item = Gio.MenuItem()
        item.set_label(self.status.split('-')[0])
        item.set_detailed_action('app.'+self.status)
        app.add_plugin_menu_item('iradio-toolbar', self.status, item)
        
        
    ## Create the stop button after starting a recording.
    def create_stop(self, action, *args):
        
        app = Gio.Application.get_default()
        app.remove_plugin_menu_item('iradio-toolbar', self.status)
        self.status = 'stop-radio'
        app = Gio.Application.get_default()
        action = Gio.SimpleAction(name=self.status)
        action.connect('activate', self.stop_radio)
        app.add_action(action)
        
        item = Gio.MenuItem()
        item.set_label(self.status.split('-')[0])
        item.set_detailed_action('app.'+self.status)
        app.add_plugin_menu_item('iradio-toolbar', self.status, item)

    def do_deactivate(self):
        app = Gio.Application.get_default()
        app.remove_plugin_menu_item('iradio-toolbar', self.status)
        
        del self.status
        del self.runningDB
        del self.uri

    def record_radio(self, action, *args):
        self.create_stop('record-radio')
        recordprocess = StreamRipperProcess(self.uri, '~/Music/')
        recordprocess.start()
        ## Replace dictionary 'running' with actual streamripper object?
        self.runningDB.update({str(self.uri):'running'})
        
        
    def stop_radio(self, action, *args):
        self.create_record('stop-radio')
        self.runningDB.update({str(self.uri):'stopped'})
        
    



class StreamRipperProcess(threading.Thread):
    def __init__(self, uri, basedirectory):
        threading.Thread.__init__(self)
        self.type = "streamripper"
        self.relay_port = None # streamripper relay port
        self.stream_name = _('Unknown')
        self.uri = uri
        self.song_info = _('Unknown')
        self.song_num = 0 # number of ripped songs
        self.song_size = 0 # file size of all ripped songs (int, in kb)
        self.current_song_size = 0 # file size of currently ripping song (int, in kb)
        self.basedirectory = basedirectory
        self.directory = self.basedirectory
        self.create_subfolder = False
        self.killed = False
        self.show_notifications = False
        self.record_until = True # False: record until stream info changes, True: record until user stops, int: Record until timestamp
        self.plan_item = ""
        self.single_file = False

    def extract_uri(self, old_uri):
        ## Need to add check for playlist files vs stream link
        try:
            f = urllib.request.urlopen(old_uri)
            url_info = str(f.info()).lower()
            
            ## MP3 Stream ##
            if "content-type: audio/mpeg" in url_info:
                final_uri = old_uri
            
            ## M3U/RAM Playlist ##
            elif "content-type: audio/x-mpegurl" in url_info or "Content-Type: audio/x-pn-realaudio" in url_info:
                print("This is a m3u playlist or ram playlist.")
                ## Split all line breaks
                url_data = f.read().decode('utf-8').splitlines()
                ## Remove all lines containing #
                uri_data = []
                for line in url_data:
                    if '#' not in line:
                        uri_data.append(line)
                ## Use first uri in list
                final_uri = uri_data[0]
            
            ## PLS Playlist ##
            elif "content-type: audio/x-scpls" in url_info:
                print("This is a pls playlist.")
                ## Split all line breaks
                url_data = f.read().decode('utf-8').splitlines()
                ## Remove all lines that don't have reference link
                uri_data = []
                for line in url_data:
                    if 'file1=' in str(line).lower():
                        uri_data.append(line.split('=')[1])
                ## Use first uri in list
                final_uri = uri_data[0]
                
            ## ASX Playlist ##
            elif "content-type: video/x-ms-asf" in url_info:
                print("This is a asx playlist.")
                ## Split all line breaks
                url_data = f.read().decode('utf-8').splitlines()
                url_data.replace("'",'"')
                ## Remove all lines that don't have reference link
                uri_data = []
                for line in url_data:
                    if 'ref href=' in line.lower():
                        uri_data.append(line.split('"')[1])
                ## Use first uri in list
                final_uri = uri_data[0]
            
            ## QTL Playlist ##
            elif "content-type: audio/x-quicktimeplayer" in url_info:
                print("This is a qtl playlist.")
                url_data = f.read().decode('utf-8').splitlines()
                url_data.replace("'",'"')
                ## Remove all lines that don't have reference link
                uri_data = []
                for line in url_data:
                    if 'src="' in line.lower():
                        uri_data.append(line.split('"')[1])
                ## Use first uri in list
                final_uri = uri_data[0]
                
            ## Unknown ##
            else:
                print("I don't even know what this could be...another audio format?")
                final_uri = old_uri
                
            return final_uri
        except Exception as e:
            print(e)
            return
    """
    Open the process
    """
    def start(self):
        final_uri = self.extract_uri(self.uri)
        options = []
        options.append("streamripper")
        options.append(final_uri)
        options.append("-t")
        if self.create_subfolder == False:
            options.append("-s")
        if self.single_file == True:
            options.append("-a")
            options.append("-A")
        options.append("-r")
        options.append("-d")
        options.append(self.basedirectory)

        print("Starting streamripper: ")       
        print(options)
'''        
        try:
            self.process = subprocess.Popen(options, 0, None, subprocess.PIPE, subprocess.PIPE, subprocess.PIPE)
        except OSError as e:
            print(_('Streamripper binary not found! ERROR: %s') % e)
            dialog = Gtk.MessageDialog(None,
             Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                     Gtk.MessageType.ERROR,
             Gtk.ButtonsType.CLOSE,
                     _('Streamripper not found!\nPlease install the streamripper package from your distribution or install it manually from: http://streamripper.sourceforge.net'))
            dialog.set_title(_('Missing binary file'))
            dialog.set_property("skip-taskbar-hint", False)
            if dialog.run() == Gtk.ResponseType.CLOSE:
                dialog.destroy()

            self.killed = True
            return False
        _thread.start_new_thread(self.reload_info, ())

    """
    Terminate process & clean incomplete files if needed
    """
    def stop(self, clean=False):
        try:
            self.process.terminate()
        except:
            pass
        # if an own subfolder is created, RecordProcess can delete incomplete files, else this must be done on program quit
        if clean == True and self.create_subfolder == True:
            try:
                shutil.rmtree(self.directory + "/incomplete")
            except:
                pass
'''
