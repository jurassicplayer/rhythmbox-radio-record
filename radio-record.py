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

from gi.repository import GObject, Gtk, Peas, RB, Gio
import subprocess, os, time, threading, shutil, urllib

class radioRecord (GObject.Object, Peas.Activatable):
    object = GObject.property (type = GObject.Object)
    
    def __init__(self):
        GObject.Object.__init__(self)
    
    def refresh_ui(self, btn_refresh=False):
        try:
            shell = self.object
            page = shell.props.selected_page
            if not hasattr(page, 'get_entry_view'):
                print('No entry view')
                return
            selected = page.get_entry_view().get_selected_entries()
            ## If selected has an entry
            if selected != []:
                ## Set empty selected entries to stopped
                multi_uri=[]
                for entry, pointer in enumerate(selected):
                    multi_uri.append(selected[entry].get_playback_uri())
                    try:
                        status = self.runningDB[str(selected[entry].get_playback_uri())]
                    except KeyError:
                        self.runningDB.update({str(selected[entry].get_playback_uri()):'stopped'})
                        status = 'stopped'
                ## If selected entries have changed
                if multi_uri != self.uri or btn_refresh == True:
                    self.uri = multi_uri
                    self.del_buttons()
                    ## If there are multiple entries
                    if len(multi_uri) > 1:
                        
                        '''
                        SELECTED ENTRIES AND RUNNINGDB ARE NOT SYNONYMOUS. 
                        I need to grab the status of selected entries, not all the ones that are in the runningDB.
                        '''
                        ## Convert runningDB values to temporary selected values
                        self.stream_status = {}
                        for x in multi_uri:
                            self.stream_status.update({x:self.runningDB[x]})
                        ## Multiline selections
                        ## If entries are all stopped 
                        if all(val == 'stopped' for val in self.stream_status.values()):
                            print('All streams are stopped')
                            self.create_record_all()
                        ## If entries are all running
                        elif all(val != 'stopped' for val in self.stream_status.values()):
                            print('All streams are running')
                            self.create_stop_all()
                        ## If entries are mixed
                        else:
                            print('Mixed streams')
                            self.create_toggle()
                            self.create_record_all()
                            self.create_stop_all()
                            
                    ## If there is only one entry
                    else:
                        ## If the entry is stopped
                        if self.runningDB[str(selected[0].get_playback_uri())] == 'stopped':
                            print('Not recording')
                            self.create_record()
                            ## self.runningDB.update({str(current_uri):'stopped'})
                        ## If the entry is recording
                        else:
                            print('Recording')
                            self.create_stop()
                
        except Exception as e:
            print(e+" exceptioned") ## Surprisingly useful to keep as this broken line since it causes a second error and rhythmbox shows both errors in full.
            pass
        return True
        
    '''
    Create Buttons
    '''    
    ## Create the recording button after stopping current recording.
    def create_record(self, *args):
        
        app = Gio.Application.get_default()
        action = Gio.SimpleAction(name='record-radio')
        action.connect('activate', self.record_radio)
        app.add_action(action)
        
        item = Gio.MenuItem()
        item.set_label('Record')
        item.set_detailed_action('app.record-radio')
        app.add_plugin_menu_item('iradio-toolbar', 'record-radio', item)
        
        
    ## Create the stop button after starting a recording.
    def create_stop(self, *args):
        
        app = Gio.Application.get_default()
        action = Gio.SimpleAction(name='stop-radio')
        action.connect('activate', self.stop_radio)
        app.add_action(action)
        
        item = Gio.MenuItem()
        item.set_label('Stop')
        item.set_detailed_action('app.stop-radio')
        app.add_plugin_menu_item('iradio-toolbar', 'stop-radio', item)
        

    ## Create the recording button after stopping current recording.
    def create_toggle(self, *args):
        
        app = Gio.Application.get_default()
        action = Gio.SimpleAction(name='toggle-radio')
        action.connect('activate', self.toggle_radio)
        app.add_action(action)
        
        item = Gio.MenuItem()
        item.set_label('Toggle')
        item.set_detailed_action('app.toggle-radio')
        app.add_plugin_menu_item('iradio-toolbar', 'toggle-radio', item)
    
    
    ## Create the recording button after stopping current recording.
    def create_record_all(self, *args):
        
        app = Gio.Application.get_default()
        action = Gio.SimpleAction(name='record-all')
        action.connect('activate', self.record_all)
        app.add_action(action)
        
        item = Gio.MenuItem()
        item.set_label('Record All')
        item.set_detailed_action('app.record-all')
        app.add_plugin_menu_item('iradio-toolbar', 'record-all', item)
        
    
    ## Create the recording button after stopping current recording.
    def create_stop_all(self, *args):
        
        app = Gio.Application.get_default()
        action = Gio.SimpleAction(name='stop-all')
        action.connect('activate', self.stop_all)
        app.add_action(action)
        
        item = Gio.MenuItem()
        item.set_label('Stop All')
        item.set_detailed_action('app.stop-all')
        app.add_plugin_menu_item('iradio-toolbar', 'stop-all', item)

    
    ## Remove all buttons
    def del_buttons(self, *args):
        app = Gio.Application.get_default()
        app.remove_plugin_menu_item('iradio-toolbar', 'stop-radio')
        app.remove_plugin_menu_item('iradio-toolbar', 'record-radio')
        app.remove_plugin_menu_item('iradio-toolbar', 'toggle-radio')
        app.remove_plugin_menu_item('iradio-toolbar', 'stop-all')
        app.remove_plugin_menu_item('iradio-toolbar', 'record-all')
    
    def do_activate(self):
        self.uri = []
        self.status = ""
        self.runningDB = {}
        
        ## Create Tool Menu
        app = Gio.Application.get_default()
        action = Gio.SimpleAction(name='Tool Menu')
        action.connect('activate', self.tool_menu)
        app.add_action(action)
        
        item = Gio.MenuItem()
        item.set_label("Radio-Record")
        item.set_detailed_action('app.radio-record')
        app.add_plugin_menu_item('tools', 'radio-record', item)
        
        self.idle_id = GObject.timeout_add(GObject.PRIORITY_DEFAULT_IDLE, self.refresh_ui)
        
    def do_deactivate(self):
        app = Gio.Application.get_default()
        
        ## Stop all running recordings
        for station in self.runningDB:
            if self.runningDB[station] != 'stopped' and self.runningDB[station]:
                recordprocess = self.runningDB[station]
                recordprocess.stop()
        
        ## Remove toolbar button
        self.del_buttons()
        del self.status
        del self.stream_status
        del self.runningDB
        del self.stream_status
        del self.uri
        GObject.source_remove(self.idle_id)

    def record_radio(self, action, *args):
        recordprocess = StreamRipperProcess(self.uri[0])
        recordprocess.start()
        ## Add streamripper instance to dictionary
        self.runningDB.update({self.uri[0] : recordprocess})
        self.refresh_ui(btn_refresh=True)
    
    def stop_radio(self, action, *args):
        ## Grab Streamripper instance from runningDB
        recordprocess = self.runningDB[self.uri[0]]
        recordprocess.stop()
        self.runningDB.update({self.uri[0]:'stopped'})
        self.refresh_ui(btn_refresh=True)
    
    def toggle_radio(self, action, *args):
        for stream in self.stream_status:
            if self.stream_status[stream] == 'stopped':
                recordprocess = StreamRipperProcess(stream)
                recordprocess.start()
                ## Add streamripper instance to dictionary
                self.runningDB.update({stream : recordprocess})
            else:
                recordprocess = self.runningDB[stream]
                recordprocess.stop()
                self.runningDB.update({stream:'stopped'})
        self.refresh_ui(btn_refresh=True)
    
    def record_all(self, action, *args):
        for stream in self.stream_status:
            if self.runningDB[stream] == 'stopped':
                recordprocess = StreamRipperProcess(stream)
                recordprocess.start()
                ## Add streamripper instance to dictionary
                self.runningDB.update({stream : recordprocess})
        self.refresh_ui(btn_refresh=True)
        
    def stop_all(self, action, *args):
        for stream in self.stream_status:
            if self.runningDB[stream] != 'stopped':
                ## Grab Streamripper instance from runningDB
                recordprocess = self.runningDB[stream]
                recordprocess.stop()
                self.runningDB.update({stream:'stopped'})
        self.refresh_ui(btn_refresh=True)
    
    def tool_menu(self):
        print("I AM THE MIGHTY TOOL MENU")
        ## Need to add a UI to set all of the options for Streamripper.
        

class StreamRipperProcess(threading.Thread):
    def __init__(self, uri):
        threading.Thread.__init__(self)
        self.type = "streamripper"
        self.relay_port = None # streamripper relay port
        self.stream_name = _('Unknown')
        self.uri = uri
        self.song_info = _('Unknown')
        self.song_num = 0 # number of ripped songs
        self.song_size = 0 # file size of all ripped songs (int, in kb)
        self.current_song_size = 0 # file size of currently ripping song (int, in kb)
        self.settings = UserConfig()
        self.basedirectory = self.get_music_dir()
        self.directory = self.basedirectory
        self.create_subfolder = self.settings.get_value('create-subfolder')
        self.separate_stream = self.settings.get_value('separate-stream')
        self.auto_delete = self.settings.get_value('auto-delete')
        self.killed = False
        ## self.record_until = True # False: record until stream info changes, True: record until user stops, int: Record until timestamp
        ## self.plan_item = ""

    def extract_uri(self, old_uri):
        try:
            f = urllib.request.urlopen(old_uri)
            url_info = str(f.info()).lower()
            
            ## MP3 Stream ##
            if "content-type: audio/mpeg" in url_info:
                final_uri = old_uri
            
            ## M3U/RAM Playlist ##
            elif "content-type: audio/x-mpegurl" in url_info or "content-type: audio/x-pn-realaudio" in url_info:
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
    
    def get_music_dir(self):
        try:
            setting_value = self.settings.get_value('music-dir')
            if str(setting_value).replace("'","") == "XDG_MUSIC_DIR":
                config_file = os.path.expanduser("~/.config/user-dirs.dirs")
                f = open(config_file, 'r')
                for line in f.read().splitlines():
                    if line.startswith("XDG_MUSIC_DIR"):
                        music_dir = line.split('=')[1].replace("\"","")
                        music_dir = music_dir.replace("$HOME", os.path.expanduser("~"))
            else:
                music_dir = os.path.expanduser(str(setting_value).replace("'",""))
        except:
            music_dir = os.path.expanduser("~")
        return music_dir
    
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
        if self.separate_stream == False:
            options.append("-a")
            options.append("-A")
        options.append("-r")
        options.append("-d")
        options.append(self.basedirectory)

        print("Starting streamripper: ")       
        print(options)

        try:
            print("Starting stream: "+ final_uri)
            self.process = subprocess.Popen(options, 0, None, subprocess.PIPE, subprocess.PIPE, subprocess.PIPE)
        except OSError as e:
            print(_('Streamripper binary not found! ERROR: %s') % e)
            dialog = Gtk.MessageDialog(None, Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.ERROR, Gtk.ButtonsType.CLOSE,
                     _('Streamripper not found!\nPlease install the streamripper package from your distribution or install it manually from: http://streamripper.sourceforge.net'))
            dialog.set_title(_('Missing binary file'))
            dialog.set_property("skip-taskbar-hint", False)
            if dialog.run() == Gtk.ResponseType.CLOSE:
                dialog.destroy()

            self.killed = True
            return False

    """
    Terminate process & clean incomplete files if needed
    """
    def stop(self):
        print("Stopping stream: "+str(self.uri))

        try:
            self.process.terminate()
        except:
            pass
        # if an own subfolder is created, RecordProcess can delete incomplete files, else this must be done on program quit
        if self.auto_delete == True and self.create_subfolder == True:
            try:
                shutil.rmtree(self.directory + "/incomplete")
            except:
                pass


class UserConfig:
    def __init__(self):
        self.SCHEMA='org.gnome.rhythmbox.plugins.radio_record'
        self.gsettings = Gio.Settings.new(self.SCHEMA)
            
    def get_value(self, key):
        try:
            if key == 'music-dir':
                value = self.gsettings.get_value(key)
            else:
                value = self.gsettings.get_boolean(key)
            print("Grabbing value for "+str(key)+" : "+ str(value))
        except:
            print("Couldn't get value")
            value = self.gsettings.get_default_value(key)
            print("Setting default value for "+ str(key) + " : " + str(value))
            self.set_value(key, value)
        return value
    def set_value(self, key, value):
        try:
            self.gsettings.set_string(key, value)
        except:
            print("Failed to set setting.")
