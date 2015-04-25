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
import concurrent.futures
import timeit

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
        self.runningDB = {}
        
        ## Create Tool Menu
        app = Gio.Application.get_default()
        action = Gio.SimpleAction(name='Tool Menu')
        action.connect('activate', self.tool_menu)
        app.add_action(action)
        
        item = Gio.MenuItem()
        item.set_label("Radio-Record")
        item.set_detailed_action('app.radio-record-prefs')
        app.add_plugin_menu_item('tools', 'radio-record-prefs', item)
        
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
        del self.stream_status
        del self.runningDB
        del self.uri
        GObject.source_remove(self.idle_id)
        GObject.source_remove(self.refresh_stream_id)

    def record_radio(self, action, *args):
        self.start_stream(self.uri[0])
        self.refresh_ui(btn_refresh=True)
        self.refresh_stream()
    
    def stop_radio(self, action, *args):
        self.stop_stream(self.uri[0])
        self.refresh_ui(btn_refresh=True)
    
    def toggle_radio(self, action, *args):
        stream_start = []
        stream_stop = []
        for stream in self.stream_status:
            if self.stream_status[stream] == 'stopped':
                stream_start.append(stream)
            else:
                self.stop_stream(stream)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_stream = dict((executor.submit(self.start_stream, stream), stream) for stream in stream_start)
        self.refresh_ui(btn_refresh=True)
        self.refresh_stream()
    
    def record_all(self, action, *args):
        start_time = timeit.default_timer()
        stream_start = []
        for stream in self.stream_status:
            if self.runningDB[stream] == 'stopped':
                stream_start.append(stream)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_stream = dict((executor.submit(self.start_stream, stream), stream) for stream in stream_start)
        elapsed_time = timeit.default_timer() - start_time
        print(elapsed_time)
        self.refresh_ui(btn_refresh=True)
        self.refresh_stream()
    
    def stop_all(self, action, *args):
        stream_stop=[]
        for stream in self.stream_status:
            if self.runningDB[stream] != 'stopped':
                self.stop_stream(stream)
        ##        stream_stop.append(stream)
        ##with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        ##    future_to_stream = dict((executor.submit(self.stop_stream, stream), stream) for stream in stream_stop)
        self.refresh_ui(btn_refresh=True)
    
    def tool_menu(self):
        print("I AM THE MIGHTY TOOL MENU")
        ## Need to add a UI to set all of the options for Streamripper.
    
    def start_stream(self, stream):
        recordprocess = StreamRipperProcess(stream)
        recordprocess.start()
        self.runningDB.update({stream : recordprocess})
        
    def stop_stream(self, stream):
        recordprocess = self.runningDB[stream]
        recordprocess.stop()
        self.runningDB.update({stream:'stopped'})
    
    def refresh_stream(self):
        time.sleep(2.5)
        dead_stream = []
        for stream in self.runningDB:
            if self.runningDB[stream] != 'stopped':
                status = self.runningDB[stream].poll_status()
                if status == 'Ended':
                    self.runningDB.update({stream:'stopped'})
                    dead_stream.append(stream)
        if dead_stream:
            self.stream_error(dead_stream)
            self.refresh_ui(btn_refresh=True)
    
    def stream_error(self, dead_streams):
        dead_list=''
        stream_name={}
        shell = self.object
        radio_page = shell.props.selected_page.props.base_query_model
        for row in radio_page:
            entry = row[0]
            stream_uri = entry.get_playback_uri()
            title = entry.get_string(RB.RhythmDBPropType.TITLE)
            stream_name.update({stream_uri:title})
        for stream in dead_streams:
            dead_list += stream_name[stream]+'\n'
        dialog = Gtk.MessageDialog(None, 0, Gtk.MessageType.WARNING, Gtk.ButtonsType.CLOSE, 'Streamripper failed to rip stream:\n'+dead_list)    
        if dialog.run() == Gtk.ResponseType.CLOSE:
            dialog.destroy()


class StreamRipperProcess(threading.Thread):
    def __init__(self, uri):
        threading.Thread.__init__(self)
        self.type = "streamripper"
        self.uri = uri
        self.settings = UserConfig()
        self.basedirectory = self.get_music_dir()
        self.directory = self.basedirectory
        self.create_subfolder = self.settings.get_value('create-subfolder')
        self.separate_stream = self.settings.get_value('separate-stream')
        self.auto_delete = self.settings.get_value('auto-delete')
    
    def recursive_hunt(self, first_uri):
        while True:
            try:
                f = urllib.request.urlopen(str(first_uri))
                url_info = str(f.info()).lower()
                text = 'content-type: audio/'
                content_types = [text+'mpeg', text+'ogg', text+'aac']
                if any(x in url_info for x in content_types):
                    break
                else: 
                    print('Recursive link, hunting deeper')
                    first_uri = self.extract_uri(first_uri)
            except Exception as e:
                ## When http response isn't known, it might be a stream, but without knowing the response I can't know for sure.
                break
        return first_uri
    
    
    def extract_uri(self, old_uri):
        try:
            
            f = urllib.request.urlopen(old_uri)
            url_info = str(f.info()).lower()
            text = 'content-type: audio/'
            playlist_type = [text+'x-mpegurl', text+'x-pn-realaudio', text+'x-scpls', text+'x-ms-asf', text+'x-quicktimeplayer']
            content_type = next(playlist for playlist in playlist_type if playlist in url_info)
            if content_type:
                ## Split all line breaks
                url_data = f.read().decode('utf-8').splitlines()
                ## Remove all lines containing unneeded information
                uri_data = []
                if content_type == playlist_type[0] or content_type == playlist_type[1]:
                    for line in url_data:
                        if '#' not in line:
                            uri_data.append(line)
                elif content_type == playlist_type[2]:
                    for line in url_data:
                        if 'file3=' in str(line).lower():
                            uri_data.append(line.split('=')[1])
                        if 'file2=' in str(line).lower():
                            uri_data.append(line.split('=')[1])
                        if 'file1=' in str(line).lower():
                            uri_data.append(line.split('=')[1])
                elif content_type == playlist_type[3]:
                    url_data.replace("'",'"')
                    for line in url_data:
                        if 'ref href=' in line.lower():
                            uri_data.append(line.split('"')[1])
                elif content_type == playlist_type[4]:
                    url_data.replace("'",'"')
                    for line in url_data:
                        if 'src="' in line.lower():
                            uri_data.append(line.split('"')[1])
                final_uri = uri_data[0]
            else:
                final_uri = old_uri
                
            return final_uri
        except Exception as e:
            print(e+"exceptioned")
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
        final_uri = self.recursive_hunt(self.uri)
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

            ## self.killed = True
            return False
    
    def get_dir_size(self, path):
        total_size = 0
        for dirpath, dirnames, filenames, in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
        return total_size
    
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
                directories = os.walk(self.basedirectory)
                watch_dir={}
                recent_dir={}
                del_folder = ''
                ## Get all subdirectories in base directory and find all incomplete directories with last modified times.
                for x in directories:
                    if 'incomplete' in x[0]:
                        folder_size = self.get_dir_size(x[0])
                        watch_dir.update({x[0]:folder_size})
                time.sleep(0.3)
                ## Check which incomplete directories are not changing.
                for x in watch_dir:
                    folder_size = self.get_dir_size(x)
                    if folder_size == watch_dir[x]:
                        recent_dir.update({x:os.stat(x).st_mtime})
                ## Get the most recent unchanging directory (hopefully the one that was most recently stopped)
                del_folder = max(recent_dir, key=recent_dir.get)
                print('Deleting: '+del_folder)
                shutil.rmtree(del_folder)
            except Exception as e:
                print(e + 'exception')
                pass
    """
    Poll streamripper status
    """
    def poll_status(self):
        print("Polling streamripper for status")
        if self.process.poll() is None:
            status = None
        else:
            status = 'Ended'
        return status

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
