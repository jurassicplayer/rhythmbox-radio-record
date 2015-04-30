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

from gi.repository import GObject, Gtk, Peas, RB, Gio, PeasGtk
import subprocess, os, time, threading, shutil, urllib, concurrent.futures, rb
import timeit


class radioRecord (GObject.Object, Peas.Activatable):
    object = GObject.property (type = GObject.Object)
    
    '''
    Class variable StreamDB
    Accessible to all instances of radioRecord
    Shared to the tool menu (radioRecord.streamDB)
    '''
    streamDB ={}
    
    def __init__(self):
        GObject.Object.__init__(self)
    
    
    """
    Plugin Integration
    """
    def do_activate(self):
        print('Radio-record plugin activated')  #debug message
        
        ## Initialize self variables
        self.button_list = set()
        self.selected = None
        ## Create Tool Menu
        # Add tool menu entry to Tools menu
        self.create_tool_menu()
        self.tool_window = Tool_Window()
        
        ## Start idle loop ## keep track of when to start new streams, stop running ones, other time-based operations.
        self.idle_id = GObject.timeout_add(GObject.PRIORITY_DEFAULT_IDLE, self.idle_loop)
        
        ## Update toolbar only on iradio selection change
        shell = self.object
        self.radio_source = shell.get_source_by_entry_type(shell.props.db.entry_type_get_by_name("iradio"))
        self.radio_source.get_entry_view().connect('selection-changed', self.update_toolbar)
        
    def do_deactivate(self):
        print('Radio-record plugin deactivated')   #debug message
        ## Remove toolbar buttons
        self.delete_all_btn()
        del self.button_list
        ## Remove tool menu
        app.remove_plugin_menu_item('tools', 'tool_menu')
        self.tool_window.destroy()
        ## Stop all running recordings
        for station in self.streamDB:
            if self.streamDB[station]['status'] != 'stopped'and self.streamDB[station]['process']:
                recordprocess = self.streamDB[station]['process']
                recordprocess.stop()
        
        ## Remove Idle Loop
        GObject.source_remove(self.idle_id)
        
        ## Delete self variables
        del self.selected
        del self.streamDB
        
    """
    UI Loop Functions
    """
    def update_toolbar(self, *args):
        print("updating toolbar")  #debug message
        ## Remove old buttons
        self.delete_all_btn()
        ## Get status of currently selected entries or add entries if not in database
        statuses = {}
        self.selected = self.radio_source.get_entry_view().get_selected_entries()
        for entry, pointer in enumerate(self.selected):
            e = self.selected[entry]
            uri = e.get_string(RB.RhythmDBPropType.LOCATION)
            try: 
                status = self.streamDB[uri]['status']
            except KeyError:
                stream_entry={
                    'title' : e.get_string(RB.RhythmDBPropType.TITLE),
                    'uri' : e.get_string(RB.RhythmDBPropType.LOCATION),
                    'song_info' : '',
                    'process' : '',
                    'status' : 'stopped'
                    }
                self.streamDB.update({uri:stream_entry})
                status = 'stopped'
            statuses.update({uri:status})
            
        if len(statuses) > 1:
            ## If entries are all stopped 
            if all(val == 'stopped' for val in statuses.values()):
                print('all stopped')
                self.create_btn('record_all', 'Record All', 'toggle_record', 'record_all')
            elif all(val != 'stopped' for val in statuses.values()):
                print('all recording')
                self.create_btn('stop_all', 'Stop All', 'toggle_record', 'stop_all')
            else:
                print('mixed recording')
                self.create_btn('toggle_record', 'Toggle', 'toggle_record')
                self.create_btn('record_all', 'Record All', 'toggle_record', 'record_all')
                self.create_btn('stop_all', 'Stop All', 'toggle_record', 'stop_all')
        else:
            try:
                ## If entry is stopped
                if statuses[uri] == 'stopped':
                    print('stream is stopped')
                    self.create_btn('start_record', 'Record', 'toggle_record')
                elif statuses[uri] != 'stopped':
                    print('stream is recording')
                    self.create_btn('stop_record', 'Stop', 'toggle_record')
            except UnboundLocalError:
                pass
    
    def idle_loop(self, *args):
        print("idle checking")  #debug message
    
    
    """
    UI Tool Menu Management
    """
    def create_tool_menu(self, *args):
        ## Create Action to Perform
        action = Gio.SimpleAction(name='tool_menu')
        action.connect('activate', self.show_tool_menu)
        ## Create Menu Entry
        item = Gio.MenuItem()
        item.set_label('Radio-Record')
        item.set_detailed_action('app.tool_menu')
        ## Insert Menu Entry
        app = Gio.Application.get_default()
        app.add_action(action)
        app.add_plugin_menu_item('tools', 'tool_menu', item)
        
    def show_tool_menu(self, *args):
        print('showing tool window')  #debug message
        self.tool_window.show_all()
    
        
    """
    UI Button Management
    """
    def create_btn(self, btn_id, label, func, *args):
        try:
            btn_arg = args[0]
        except:
            btn_arg = None
        ## Create Action to Perform
        action = Gio.SimpleAction(name=btn_id)
        action.connect('activate', getattr(self, func), btn_arg)
        action.connect('activate', self.update_toolbar)
        ## Create Menu Entry
        item = Gio.MenuItem()
        item.set_label(label)
        item.set_detailed_action('app.'+btn_id)
        ## Insert Menu Entry
        app = Gio.Application.get_default()
        app.add_action(action)
        app.add_plugin_menu_item('iradio-toolbar', btn_id, item)
        self.button_list.add(btn_id)
        
    def delete_btn(self, btn_id, *args):
        app = Gio.Application.get_default()
        app.remove_plugin_menu_item('iradio-toolbar', btn_id)
        
    def delete_all_btn(self, *args):
        for button in self.button_list:
            self.delete_btn(button)
    
    
    """
    Button Recording Management
    """
    def toggle_record(self, action, unk, *args):
        uris = []
        for entry, pointer in enumerate(self.selected):
            uris.append(self.selected[entry].get_playback_uri())
        for uri in uris:
            if self.streamDB[uri]['status'] == 'recording' and 'record_all' not in args:
                self.stop_stream(uri)
                self.streamDB[uri]['status'] = 'stopped'
            elif self.streamDB[uri]['status'] == 'stopped' and 'stop_all' not in args:
                self.start_stream(uri)
                self.streamDB[uri]['status'] = 'recording'


    """
    Stream Management
    """
    def start_stream(self, stream):
        recordprocess = StreamRipperProcess(stream)
        recordprocess.start()
        self.streamDB[stream].update({'process' : recordprocess})
        
    def stop_stream(self, stream):
        print("stopping stream")
        recordprocess = self.streamDB[stream]['process']
        recordprocess.stop()
        self.streamDB[stream].update({'process' : ''})

"""
Streamripper Process
"""
class StreamRipperProcess(threading.Thread):
    def __init__(self, uri):
        threading.Thread.__init__(self)
        self.type = "streamripper"
        self.uri = uri
        self.settings = UserConfig()
        self.basedirectory = self.settings.get_value('music-dir')
        self.create_subfolder = self.settings.get_value('create-subfolder')
        self.separate_stream = self.settings.get_value('separate-stream')
        self.auto_delete = self.settings.get_value('auto-delete')
        self.relay_port = ''
        self.song_info = ''
        self.stream_name = ''
        self.song_num = 0
        self.song_size = 0
        self.current_song_size = 0
        self.killed = False

    
    """
    Open the process
    """
    def start(self):
        final_uri = MiscTools.recursive_hunt(self.uri)
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
        t = threading.Thread(target=self.refresh_info)
        t.start()
    
    
    """
    Terminate process & clean incomplete files if needed
    """
    def stop(self):
        print("Stopping stream: "+str(self.uri))

        try:
            self.process.terminate()
        except:
            pass
        if self.auto_delete == True and self.create_subfolder == True:
            try:
                ## Strip out invalid characters from folder name 
                stream = self.stream_name.replace('~', '').replace('#', '').replace('%', '').replace('*', '').replace('{', '').replace('}', '').replace('\\', '').replace(':', '').replace('<', '').replace('>', '').replace('?', '').replace('/', '').replace('+', '').replace('|', '-').replace('"', '')
                del_folder = self.basedirectory+"/"+stream+"/incomplete"
                print('Deleting: '+del_folder)
                shutil.rmtree(del_folder)
            except Exception as e:
                print(e + 'exception')
                pass
    
    '''
    def print_info(self):
        print(self.relay_port)
        print(self.stream_name) # Directory created is the same name as this (convert some characters to work for filesystem)
        print(self.song_info)
        print(self.song_num)
        print(self.song_size)
        print(self.current_song_size)
    '''
        
    """
    Poll streamripper status
    """
    def refresh_info(self):
        print("Polling streamripper for status")
        pout = self.process.stdout
        while self.process.poll() == None:
            line = ""
            while True:
                try:
                    char = pout.read(1).decode("utf-8")
                except:
                    break
                
                if char == None or char == "":
                    break
                if char == "\n":
                    break
                if char == "\r":
                    break
                line = line+char
            if line.startswith("relay port"):
                self.relay_port = line.split(":")[1].strip()
            if line.startswith("stream"):
                self.stream_name = line.split(":")[1].strip()
            if line.startswith("[ripping") or line.startswith("[skipping"):
                if not (self.song_info == line[17:-10]):
                    # When song info changes
                    self.song_num += 1
                    self.song_size = float(self.song_size) + float(self.current_song_size)
                self.current_song_size = float( MiscTools.parse_size(line[len(line)-8:len(line)-1].strip()) )
                self.song_info = line[17:-10]
        self.killed = True
        return False

class MiscTools:
    """
    Recursively opens playlist urls to find the audio stream
    returns: string
    """
    def recursive_hunt(first_uri):
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
    
    """
    Parse size info e.g. 742kb, 1,2M to int in kb
    returns: int size (in kb)
    """
    def parse_size(str):
        format = ""
        if str.strip() == "0b":
            return 0
        if "," in str:
            intsize = int(str.split(",")[0])
            floatsize = float( str[0:len(str)-2].replace(",", ".") )
            format = str[len(str)-1:len(str)]
            if format == "kb":
                return intsize
            if format == "M":
                return floatsize*1000
        format_kb = str[len(str)-2:len(str)]
        format_mb = str[len(str)-1:len(str)]
        if format_kb == "kb":
            format = "kb"
        if format_mb == "M":
            format = "mb"
        num = float( str[0:len(str)-2] )
        if format == "kb":
            return num
        if format == "mb":
            return num*1000
        return num
    """
    Convert size (int) in kb to string (KB/MB/GB)
    returns: string
    """
    def convert_size(size):
        if size >= 1000000:
            return str(size / 1000000) + " GB"
        if size >= 1000:
            return str(size / 1000) + " MB"
        return str(size) + " KB"
    
    """
    Converts XDG_MUSIC_DIR and relative locations to full paths
    returns: string
    """
    def get_full_dir(value):
        try:
            if str(value).replace("'","") == "XDG_MUSIC_DIR":
                config_file = os.path.expanduser("~/.config/user-dirs.dirs")
                f = open(config_file, 'r')
                for line in f.read().splitlines():
                    if line.startswith("XDG_MUSIC_DIR"):
                        music_dir = line.split('=')[1].replace("\"","")
                        music_dir = music_dir.replace("$HOME", os.path.expanduser("~"))
            else:
                music_dir = os.path.expanduser(str(value).replace("'",""))
        except:
            music_dir = os.path.expanduser("~")
        return music_dir

"""
Super Simplistic Settings Manager
"""
class UserConfig:
    def __init__(self):
        self.SCHEMA='org.gnome.rhythmbox.plugins.radio_record'
        self.gsettings = Gio.Settings.new(self.SCHEMA)
            
    def get_value(self, key):
        try:
            if key == 'music-dir':
                value = MiscTools.get_full_dir(self.gsettings.get_value(key))
            else:
                value = self.gsettings.get_boolean(key)
            print("Grabbing value for "+str(key)+" : "+ str(value))
        except:
            print("Couldn't get value")
            value = self.gsettings.get_default_value(key)
            self.set_value(key, value)
        return value
    def set_value(self, key, value):
        try:
            if key == 'music-dir':
                self.gsettings.set_string(key, value)
            else:
                self.gsettings.set_boolean(key, value)
        except:
            print("Failed to set setting.")
    
"""
Preferences Menu
"""
class Preferences(GObject.Object, PeasGtk.Configurable):
    __gtype_name__ = 'Radio_Record_Preferences'
    object = GObject.property(type=GObject.Object)
    
    def __init__(self):
        GObject.Object.__init__(self)
        self.settings = UserConfig()
        
    def do_create_configure_widget(self):
        handlers = {
            "onFileSet": self.onFileSet
            }
        self.pref_menu = Gtk.Builder()
        self.pref_menu.add_from_file(rb.find_plugin_file(self, 'ui/preferences.ui'))
        self.pref_menu.connect_signals(handlers)
        ## Set current settings to preferences window 
        self.pref_menu.get_object('save-folder-button').set_current_folder(self.settings.get_value('music-dir'))
        settings = ['create-subfolder', 'separate-stream', 'auto-delete']
        for entry in settings:
            self.pref_menu.get_object(entry+'-toggle').set_active(self.settings.get_value(entry))
            ## Bind setting toggles to settings
            self.settings.gsettings.bind(entry, self.pref_menu.get_object(entry+'-toggle'), 'active', Gio.SettingsBindFlags.DEFAULT)
            
        return self.pref_menu.get_object('PrefWindow')

    def onFileSet(self, *args):
        music_dir = self.pref_menu.get_object('save-folder-button').get_filename()
        self.settings.set_value('music-dir', music_dir)
        
"""
Tools Menu - Record and Plan Manager
"""
class Tool_Window(Gtk.Window):
    def __init__(self, *args): ## Need runningDB, rhythmbox radio stations,
        for arg in args:
            print(arg)
        Gtk.Window.__init__(self, title="Radio-Record Tools")
        self.set_default_geometry(550,300)
        self.set_border_width(5)
        
        """
        Main Container
        parent: tool window
        """
        main_container = Gtk.Box(spacing=5)
        main_container.set_orientation(Gtk.Orientation.VERTICAL)
        self.add(main_container)
        
        """
        Main Stack Container
        parent: main container
        """
        self.stack_container = stack_container = Gtk.Stack()
        stack_container.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        stack_container.set_transition_duration(500)
        stack_switcher = Gtk.StackSwitcher()
        stack_switcher.set_stack(stack_container)
        main_container.add(stack_switcher)
        stack_switcher.set_halign(Gtk.Align.CENTER)
        main_container.pack_start(stack_container, True, True, 0)
        
        """
        Record Manager Container
        parent: main stack
        """
        record_manager = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        stack_container.add_titled(record_manager, "record-manager", "Record")
        ## Scrollable Treeview
        
        ## Button Bar
        button_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        stop_btn = self.generate_button(Gtk.STOCK_STOP, "Stop", "onStopRecord")
        stop_all_btn = self.generate_button(Gtk.STOCK_CLEAR, "Stop all", "onStopRecord", "all")
        button_bar.add(stop_btn)
        button_bar.add(stop_all_btn)
        record_manager.add(button_bar)
        
        """
        Plan Manager Container
        parent: main stack
        """
        self.plan_manager = plan_manager = Gtk.Stack()
        plan_manager.set_transition_type(Gtk.StackTransitionType.SLIDE_UP_DOWN)
        plan_manager.set_transition_duration(500)
        plan_view_edit_switcher = Gtk.StackSwitcher()
        plan_view_edit_switcher.set_stack(plan_manager)
        stack_container.add_titled(plan_manager, "plan-manager", "Plan")
        
        """
        Plan Viewer Container
        parent: plan manager
        """
        plan_viewer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        plan_manager.add_named(plan_viewer, "plan-viewer")
        
        ## Button bar
        button_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        add_btn = self.generate_button(Gtk.STOCK_ADD, "Add", "onEdit", "add")
        edit_btn = self.generate_button(Gtk.STOCK_EDIT, "Edit", "onEdit")
        delete_btn = self.generate_button(Gtk.STOCK_DELETE, "Delete", "onDelete")
        button_bar.add(add_btn)
        button_bar.add(edit_btn)
        button_bar.add(delete_btn)
        plan_viewer.add(button_bar)
        
        """
        Plan Editor Container
        parent: plan manager
        """
        plan_editor = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        plan_manager.add_named(plan_editor, "plan-editor")
        
        ## Button bar
        button_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        save_btn = self.generate_button(Gtk.STOCK_SAVE, "Save", "onSave")
        cancel_btn = self.generate_button(Gtk.STOCK_CANCEL, "Cancel", "onCancel")
        button_bar.pack_end(save_btn, False, False, 0)
        button_bar.pack_end(cancel_btn, False, False, 0)
        plan_editor.add(button_bar)
        
        
        """
        Close Button
        parent: main container
        """
        close_btn = self.generate_button(Gtk.STOCK_CLOSE, "Close", "onClose")
        main_container.pack_end(close_btn, False, False, 0)
        
    
    def generate_button(self, image, label, action, *args):
        try:
            btn_arg = args[0]
        except:
            btn_arg = None
        button = Gtk.Button.new_from_icon_name(image, Gtk.IconSize.BUTTON)
        button.set_always_show_image(True)
        button.set_label(label)
        button.connect("clicked", getattr(self, action), btn_arg)
        return button
    
    """
    Record Manager Button Functions
    """
    def onStopRecord(self, *args):
        stream_list=[]
        if "all" in args:
            print('stop all recordings') ## Just get list of streams to stop
            '''
            for entry in everything:
                .get_something something value
            stream_list.append(uri)
            '''
        else:
            print('stopping recording')
            '''
            for entry in selected:
                .get_something something value
            stream_list.append(uri)
            '''
        ## stop streams here
        for stream in stream_list:
            self.stop_stream(stream)
    """
    Tool Menu Stream Management
    """
    def stop_stream(self, stream):
        print("stopping stream")
        recordprocess = radioRecord.streamDB[stream]['process']
        recordprocess.stop()
        radioRecord.streamDB[stream].update({'process' : ''})
    

    """
    Plan Manager Button Functions
    """
    def onEdit(self, *args):
        if "add" in args:
            print("Initializing options")
        self.plan_manager.set_visible_child_name('plan-editor')
    def onDelete(self, *args):
        print('deleting plan')
    def onCancel(self, *args):
        self.plan_manager.set_visible_child_name('plan-viewer')
    def onSave(self, *args):
        print('saving plan')
        self.plan_manager.set_visible_child_name('plan-viewer')
    """
    Main Container Button Functions
    """
    def onClose(self, *args):
        self.hide()
