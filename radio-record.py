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

temp_planning_list = [
    ('Station', 'Stream', 0, 'SMTWHFA', 8, 30, 45),
    ('AnimeNfo', 'http://itori.animenfo.com:443/listen.pls', 0, 'MWF', 9, 30, 120),
    ('Station', 'Stream', 0, 'SA', 8, 30, 45),
    ('Station', 'Stream', 0, 'TH', 8, 30, 45)
    ]

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
        app = Gio.Application.get_default()
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
        ##del self.streamDB
        
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
                stream_info = self.streamDB[uri]
                stream_info.update({
                    'title' : e.get_string(RB.RhythmDBPropType.TITLE),
                    'uri' : e.get_string(RB.RhythmDBPropType.LOCATION)
                    })
                status = stream_info['status']
            except KeyError:
                stream_entry={
                    'title' : e.get_string(RB.RhythmDBPropType.TITLE),
                    'uri' : e.get_string(RB.RhythmDBPropType.LOCATION),
                    'song_info' : '',
                    'song_num' : '',
                    'song_size' : '',
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
        self.tool_window.visible = True
    
        
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
            radioRecord.streamDB[self.uri]['status'] = 'stopped'
            radioRecord.streamDB[self.uri]['process'] = ''
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
                del_folder = str(self.basedirectory)+"/"+str(stream)+"/incomplete/"
                print('Deleting: '+del_folder)
                shutil.rmtree(del_folder, ignore_errors=True)
            except Exception as e:
                print(e + 'exception')
                pass
    
        
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
            radioRecord.streamDB[self.uri]['song_info'] = self.song_info
            radioRecord.streamDB[self.uri]['song_num'] = self.song_num
            radioRecord.streamDB[self.uri]['song_size'] = self.song_size
        self.killed = True
        if radioRecord.streamDB[self.uri]['status'] != 'stopped':
            dialog = Gtk.MessageDialog(None, 0, Gtk.MessageType.WARNING, Gtk.ButtonsType.CLOSE, 'Streamripper failed to rip stream:\n'+radioRecord.streamDB[self.uri]['title'])
            radioRecord.streamDB[self.uri]['status'] = 'stopped'
            radioRecord.streamDB[self.uri]['process'] = ''
            if dialog.run() == Gtk.ResponseType.CLOSE:
                dialog.destroy()
        return False
        
        def stream_error(self):
            dialog = Gtk.MessageDialog(None, 0, Gtk.MessageType.WARNING, Gtk.ButtonsType.CLOSE, 'Streamripper failed to rip stream:\n'+self.uri)
            radioRecord.streamDB[self.uri]['status'] = 'stopped'
            radioRecord.streamDB[self.uri]['process'] = ''
            if dialog.run() == Gtk.ResponseType.CLOSE:
                dialog.destroy()
        

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
    def __init__(self, *args):
        self.visible = None
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
        ## Treeview
        self.record_liststore = record_liststore = Gtk.ListStore(str, str, str)
        self.record_liststore.set_sort_func(2, self.sort_song_num, None)
        self.treeview = treeview = Gtk.TreeView.new_with_model(self.record_liststore)
        ts = treeview.get_selection()
        ts.set_mode(Gtk.SelectionMode.MULTIPLE)
        for i, column_title in enumerate(['Station', 'Current Song', 'Recorded']):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(column_title, renderer, text=i)
            column.set_sort_column_id(i)
            treeview.append_column(column)
        ## Scroll Window
        scrollable_treelist = Gtk.ScrolledWindow()
        scrollable_treelist.set_vexpand(True)
        scrollable_treelist.add(treeview)
        record_manager.pack_start(scrollable_treelist, True, True, 0)
        
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
        ## Plan editor container
        editor_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        editor_container.set_homogeneous(False)
        plan_editor.add(editor_container)
        ## Editor options container
        editor_options = Gtk.Grid(expand=True)
        editor_options.set_column_spacing(10)
        editor_options.set_column_homogeneous(True)
        editor_options.set_halign(Gtk.Align.FILL)
        editor_container.pack_start(editor_options, True, True, 0)
        radio_label = Gtk.Label('Radio Station')
        start_time_label = Gtk.Label('Start Time')
        duration_label = Gtk.Label('Duration')
        time_colon = Gtk.Label(':')
        time_colon2 = Gtk.Label(':')
        colon_multiplier = 10
        editor_options.attach(radio_label, 0,0,1*colon_multiplier,1)
        
        self.radio_combotext = radio_combotext = Gtk.ComboBoxText()
        editor_options.attach(radio_combotext, 0,1,2*colon_multiplier,1)
        
        editor_options.attach(start_time_label, 0,2,1*colon_multiplier,1)
        
        self.hour_time = hour_time = Gtk.SpinButton.new_with_range(0,12,1)
        editor_options.attach(hour_time, 0,3,1*colon_multiplier,1)
        
        editor_options.attach(time_colon, 1*colon_multiplier,3,1,1)
        
        self.minute_time = minute_time = Gtk.SpinButton.new_with_range(0,59,1)
        editor_options.attach(minute_time, 1*colon_multiplier+1,3,1*colon_multiplier,1)
        
        self.ampm_combotext = ampm_combotext = Gtk.ComboBoxText()
        ampm_combotext.append('am', 'am')
        ampm_combotext.append('pm', 'pm')
        ampm_combotext.set_active(0)
        editor_options.attach(ampm_combotext, 2*colon_multiplier+1,3,1*colon_multiplier/2,1)
        
        editor_options.attach(duration_label, 0,4,1*colon_multiplier,1)
        
        self.hour_duration = hour_duration = Gtk.SpinButton.new_with_range(0,999,1)
        editor_options.attach(hour_duration, 0,5,1*colon_multiplier,1)
        
        editor_options.attach(time_colon2, 1*colon_multiplier,5,1,1)
        
        self.minute_duration = minute_duration = Gtk.SpinButton.new_with_range(0,999,1)
        editor_options.attach(minute_duration, 1*colon_multiplier+1,5,1*colon_multiplier,1)
        
        ## Editor day of week container
        
        self.repeat_checkbox = repeat_checkbox = Gtk.CheckButton.new_with_label('Repeat')
        repeat_checkbox.connect('notify::active', self.onRepeatToggle)
        editor_options.attach(repeat_checkbox, 3*colon_multiplier+1,0,1*colon_multiplier/2,1)
        # Day of week stack
        self.dow_stack = dow_stack = Gtk.Stack()
        dow_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        dow_stack.set_transition_duration(500)
        dow_switcher = Gtk.StackSwitcher()
        dow_switcher.set_stack(dow_stack)
        editor_options.attach(dow_stack, 3*colon_multiplier+1,1,1*colon_multiplier/2,7)
        self.blank_stack = blank_stack = Gtk.Box()
        dow_stack.add_named(blank_stack, "blank_stack")
        
        weekday_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        dow_stack.add_named(weekday_container, 'btn_stack')
        week = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
        self.week_btns = []
        for day in week:
            button = Gtk.ToggleButton.new_with_label(day)
            self.week_btns.append(button)
            weekday_container.add(button)
        
        ## Button bar
        button_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        save_btn = self.generate_button(Gtk.STOCK_SAVE, "Save", "onSave")
        cancel_btn = self.generate_button(Gtk.STOCK_CANCEL, "Cancel", "onCancel")
        button_bar.add(cancel_btn)
        button_bar.add(save_btn)
        plan_editor.add(button_bar)
        
        
        """
        Close Button
        parent: main container
        """
        close_btn = self.generate_button(Gtk.STOCK_CLOSE, "Close", "onClose")
        main_container.pack_end(close_btn, False, False, 0)
        
        t = threading.Thread(target=self.refresh_info)
        t.start()
        
    """
    Tool Menu Information Refresh 
    """    
    def refresh_info(self):
        while True:
            while self.visible == True:
                self.update_recordDB()
                break
            time.sleep(15)
    def update_recordDB(self):
        listDB = {}
        streamDB = {}
        # Get list of stream names that are currently recording
        for entry in radioRecord.streamDB:
            if radioRecord.streamDB[entry]['status'] == 'recording':
                streamDB.update({radioRecord.streamDB[entry]['title']: radioRecord.streamDB[entry]})
        # Get list of stream names that are currently in the liststore
        for i, row in enumerate(self.record_liststore):
            listDB.update({self.record_liststore[i][0]: i})
        # Compare dictionaries
        for entry in streamDB:
            info = [streamDB[entry]['title'], streamDB[entry]['song_info'], str(streamDB[entry]['song_num'])+' songs ('+MiscTools.convert_size(streamDB[entry]['song_size'])+')']
            try:
                ## Update current listing
                self.record_liststore[listDB[entry]] = info
            except KeyError:
                self.record_liststore.append(info)
                
    
    def sort_song_num(self, model, row1, row2, data):
        sort_column, _ = model.get_sort_column_id()
        value1 = model.get_value(row1, sort_column)
        value2 = model.get_value(row2, sort_column)
        value1 = int(value1.split(" ")[0])
        value2 = int(value2.split(" ")[0])
        if value1 < value2:
            return -1
        elif value1 == value2:
            return 0
        else:
            return 1
    
    
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
        ts = self.treeview
        if "all" in args:
            ts.get_selection().select_all()
        (model, pathlist) = ts.get_selection().get_selected_rows()
        for path in pathlist:
            tree_iter = model.get_iter(path)
            stream_list.append(tree_iter)

        ## stop streams here
        for tree_iter in stream_list:
            stream_name = model.get_value(tree_iter, 0)
            model.remove(tree_iter)
            for uri in radioRecord.streamDB:
                if radioRecord.streamDB[uri]['title'] == stream_name:
                    print('stop stream '+str(uri))
                    self.stop_stream(uri)
                
                
    """
    Tool Menu Stream Management
    """
    def stop_stream(self, stream):
        recordprocess = radioRecord.streamDB[stream]['process']
        recordprocess.stop()
        radioRecord.streamDB[stream].update({
            'process' : '',
            'status' : 'stopped'
            })
    

    """
    Plan Manager Button Functions
    """
    def onRepeatToggle(self, switch, gparam):
        if switch.get_active():
            self.dow_stack.set_visible_child_name('btn_stack')
        else:
            self.dow_stack.set_visible_child_name('blank_stack')
    def onEdit(self, *args):
        if "add" in args:
            print("Initializing options")
            self.ampm_combotext.set_active(0)
            self.repeat_checkbox.set_active(True)
            self.dow_stack.set_visible_child_name('btn_stack')
        else:
            print('Setting known options')
            # Set station
            # Set hour start
            # Set minute start
            # Set am/pm
            # Set hour duration
            # Set minute duration
            # Set repeat toggle
            # Set day of week
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
        self.visible = None
        self.hide()
