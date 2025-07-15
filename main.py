import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog, ttk
import socket
import ssl
import threading
import re
from datetime import datetime
import json
import os
import webbrowser
import pytchat
import requests
from urllib.parse import urlparse, parse_qs

TWITCH_SERVER = 'irc.chat.twitch.tv'
TWITCH_PORT = 6697
TOKEN_HELP_URL = "https://twitchtokengenerator.com"
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

def get_config_path():
    appdata = os.getenv('APPDATA')
    if appdata:
        config_dir = os.path.join(appdata, 'Chat')
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, 'config.json')
    else:
        return 'chat_settings.json'

SETTINGS_FILE = get_config_path()

class MultiPlatformChat:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Chat")
        self.root.geometry("500x700")
        self.root.configure(bg='#18181b')
        
        self.overlay_mode = False
        self.transparency = 0.9
        
        self.create_ui()
        
        self.twitch_sock = None
        self.youtube_chat = None
        self.connected_services = {
            'twitch': False,
            'youtube': False
        }
        self.chat_threads = []
        self.twitch_token = None
        self.twitch_channel = None
        self.youtube_video_id = None
        self.youtube_api_key = None
        
        self.load_settings()
        
    def create_ui(self):
        self.create_header()
        self.create_chat_display()
        self.create_connection_controls()
        self.create_overlay_controls()
        
    def create_header(self):
        self.header = tk.Frame(self.root, bg='#333333', height=30, cursor="fleur")
        self.header.pack(fill=tk.X)
        
        self._offset_x = 0
        self._offset_y = 0
        self.header.bind("<Button-1>", self.start_move)
        self.header.bind("<B1-Motion>", self.on_move)
        
        close_btn = tk.Button(self.header, text="×", bg='#333333', fg='white', 
                            borderwidth=0, command=self.on_closing, font=('Comic Sans MS', 12))
        close_btn.pack(side=tk.RIGHT, padx=5)
        
        self.overlay_btn = tk.Button(self.header, text="👁", bg='#333333', fg='white', 
                              borderwidth=0, command=self.toggle_overlay_mode, font=('Comic Sans MS', 10))
        self.overlay_btn.pack(side=tk.RIGHT, padx=2)
        
        title_label = tk.Label(self.header, text="Chat", bg='#333333', 
                             fg='white', font=('Comic Sans MS', 10))
        title_label.pack(side=tk.LEFT, padx=10)
        
    def create_chat_display(self):
        self.chat_display = scrolledtext.ScrolledText(
            self.root, wrap=tk.WORD, bg='#18181b', fg='white',
            font=('Comic Sans MS', 10), insertbackground='white'
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.chat_display.config(state=tk.DISABLED)
        
        self.chat_display.tag_configure("system", foreground="#ffaa00")
        self.chat_display.tag_configure("timestamp", foreground="#888888")
        self.chat_display.tag_configure("twitch_username", foreground="#9147ff")
        self.chat_display.tag_configure("youtube_username", foreground="#ff0000")
        self.chat_display.tag_configure("message", foreground="#ffffff")
        self.chat_display.tag_configure("help", foreground="#9147ff", underline=1)
        
    def create_connection_controls(self):
        self.conn_frame = tk.Frame(self.root, bg='#18181b')
        self.conn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        twitch_frame = tk.LabelFrame(self.conn_frame, text="Twitch", bg='#18181b', fg='#9147ff', font=('Comic Sans MS', 9))
        twitch_frame.pack(fill=tk.X, pady=2)
        
        self.twitch_channel_var = tk.StringVar()
        tk.Label(twitch_frame, text="Channel:", bg='#18181b', fg='white', font=('Comic Sans MS', 9)).pack(side=tk.LEFT, padx=5)
        tk.Entry(twitch_frame, textvariable=self.twitch_channel_var, bg='#2d2d2d', fg='white',
                insertbackground='white', font=('Comic Sans MS', 9)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        self.twitch_connect_btn = tk.Button(
            twitch_frame, text="Connect", bg='#9147ff', fg='white',
            command=lambda: self.toggle_connection('twitch'), font=('Comic Sans MS', 9)
        )
        self.twitch_connect_btn.pack(side=tk.RIGHT, padx=5)
        
        youtube_frame = tk.LabelFrame(self.conn_frame, text="YouTube", bg='#18181b', fg='#ff0000', font=('Comic Sans MS', 9))
        youtube_frame.pack(fill=tk.X, pady=2)
        
        self.youtube_input_var = tk.StringVar()
        tk.Label(youtube_frame, text="Channel/Video:", bg='#18181b', fg='white', font=('Comic Sans MS', 9)).pack(side=tk.LEFT, padx=5)
        youtube_entry = tk.Entry(youtube_frame, textvariable=self.youtube_input_var, bg='#2d2d2d', fg='white',
                insertbackground='white', font=('Comic Sans MS', 9))
        youtube_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        self.youtube_connect_btn = tk.Button(
            youtube_frame, text="Connect", bg='#ff0000', fg='white',
            command=lambda: self.toggle_connection('youtube'), font=('Comic Sans MS', 9)
        )
        self.youtube_connect_btn.pack(side=tk.RIGHT, padx=5)
        
        status_frame = tk.Frame(self.root, bg='#18181b')
        status_frame.pack(fill=tk.X, padx=5, pady=2)
        
        self.status_var = tk.StringVar(value="Disconnected from both services")
        tk.Label(
            status_frame, textvariable=self.status_var, bg='#18181b', fg='white',
            font=('Comic Sans MS', 8)
        ).pack(side=tk.LEFT)
        
        tk.Label(
            status_frame, text="Get Twitch Token", bg='#18181b', fg='#9147ff',
            font=('Comic Sans MS', 8, 'underline'), cursor="hand2"
        ).pack(side=tk.RIGHT)
        status_frame.winfo_children()[-1].bind("<Button-1>", lambda e: webbrowser.open(TOKEN_HELP_URL))
        
    def create_overlay_controls(self):
        self.overlay_frame = tk.Frame(self.root, bg='#18181b')
        self.overlay_frame.pack(fill=tk.X, padx=5, pady=2)
        
        overlay_label = tk.Label(self.overlay_frame, text="Overlay Mode:", bg='#18181b', fg='white', font=('Comic Sans MS', 9))
        overlay_label.pack(side=tk.LEFT, padx=5)
        
        self.overlay_var = tk.BooleanVar()
        overlay_check = tk.Checkbutton(self.overlay_frame, variable=self.overlay_var, 
                                     bg='#18181b', fg='white', selectcolor='#2d2d2d',
                                     command=self.toggle_overlay_mode, font=('Comic Sans MS', 9))
        overlay_check.pack(side=tk.LEFT)
        
        tk.Label(self.overlay_frame, text="Transparency:", bg='#18181b', fg='white', font=('Comic Sans MS', 9)).pack(side=tk.LEFT, padx=(20, 5))
        
        self.transparency_var = tk.DoubleVar(value=90)
        self.transparency_scale = tk.Scale(self.overlay_frame, from_=10, to=100, orient=tk.HORIZONTAL,
                                         variable=self.transparency_var, bg='#18181b', fg='white',
                                         highlightthickness=0, command=self.update_transparency, font=('Comic Sans MS', 8))
        self.transparency_scale.pack(side=tk.LEFT, padx=5)
        
    def start_move(self, event):
        self._offset_x = event.x
        self._offset_y = event.y
        
    def on_move(self, event):
        x = self.root.winfo_x() + event.x - self._offset_x
        y = self.root.winfo_y() + event.y - self._offset_y
        self.root.geometry(f"+{x}+{y}")
            
    def toggle_overlay_mode(self):
        self.overlay_mode = not self.overlay_mode
        self.overlay_var.set(self.overlay_mode)
        
        if self.overlay_mode:
            self.root.wm_attributes('-topmost', True)
            self.root.overrideredirect(True)
            self.conn_frame.pack_forget()
            self.overlay_frame.pack_forget()
            self.header.configure(height=20)
            self.root.geometry("400x300")
            self.update_transparency()
        else:
            self.root.wm_attributes('-topmost', False)
            self.root.overrideredirect(False)
            self.conn_frame.pack(fill=tk.X, padx=5, pady=5)
            self.overlay_frame.pack(fill=tk.X, padx=5, pady=2)
            self.header.configure(height=30)
            self.root.geometry("500x700")
            self.root.wm_attributes('-alpha', 1.0)
            
    def update_transparency(self, value=None):
        if self.overlay_mode:
            alpha = self.transparency_var.get() / 100.0
            self.root.wm_attributes('-alpha', alpha)
            
    def get_live_video_from_channel(self, channel_input):
        if not self.youtube_api_key:
            self.youtube_api_key = self.prompt_youtube_api_key()
            if not self.youtube_api_key:
                return None
                
        try:
            if channel_input.startswith('@'):
                channel_input = channel_input[1:]
                
            if channel_input.startswith('UC') and len(channel_input) == 24:
                channel_id = channel_input
            else:
                search_url = f"{YOUTUBE_API_BASE}/search"
                params = {
                    'part': 'snippet',
                    'q': channel_input,
                    'type': 'channel',
                    'maxResults': 1,
                    'key': self.youtube_api_key
                }
                
                response = requests.get(search_url, params=params)
                data = response.json()
                
                if 'items' not in data or not data['items']:
                    return None
                    
                channel_id = data['items'][0]['snippet']['channelId']
            
            search_url = f"{YOUTUBE_API_BASE}/search"
            params = {
                'part': 'snippet',
                'channelId': channel_id,
                'eventType': 'live',
                'type': 'video',
                'maxResults': 1,
                'key': self.youtube_api_key
            }
            
            response = requests.get(search_url, params=params)
            data = response.json()
            
            if 'items' in data and data['items']:
                return data['items'][0]['id']['videoId']
                
        except Exception as e:
            self.add_system_message(f"YouTube API error: {e}")
            
        return None
        
    def prompt_youtube_api_key(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("YouTube API Key")
        dialog.resizable(False, False)
        dialog.configure(bg='#18181b')
        
        instructions = (
            "To auto-detect live streams, you need a YouTube API key:\n\n"
            "1. Go to console.cloud.google.com\n"
            "2. Create a new project or select existing\n"
            "3. Enable YouTube Data API v3\n"
            "4. Create credentials (API key)\n"
            "5. Copy the API key below:\n\n"
            "Note: You only need to do this once unless the API key gets reset."
        )
        tk.Label(dialog, text=instructions, bg='#18181b', fg='white',
                justify=tk.LEFT, font=('Comic Sans MS', 10)).pack(padx=10, pady=10)
        
        api_key_entry = tk.Entry(dialog, width=50, bg='#2d2d2d', fg='white',
                               insertbackground='white', font=('Comic Sans MS', 10))
        api_key_entry.pack(padx=10, pady=5)
        
        result = [None]
        
        def on_submit():
            key = api_key_entry.get().strip()
            if key:
                result[0] = key
                dialog.destroy()
            
        def on_skip():
            dialog.destroy()
            
        btn_frame = tk.Frame(dialog, bg='#18181b')
        btn_frame.pack(pady=10)
        
        tk.Button(btn_frame, text="Submit", bg='#ff0000', fg='white',
                 command=on_submit, font=('Comic Sans MS', 10)).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Skip (Manual Video ID)", bg='#666666', fg='white',
                 command=on_skip, font=('Comic Sans MS', 10)).pack(side=tk.LEFT, padx=5)
        
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")
        
        self.root.wait_window(dialog)
        return result[0]
        
    def extract_video_id_from_url(self, url):
        if 'youtube.com/watch' in url:
            parsed = urlparse(url)
            return parse_qs(parsed.query).get('v', [None])[0]
        elif 'youtu.be/' in url:
            return url.split('youtu.be/')[-1].split('?')[0]
        return None
        
    def add_message(self, platform, username, message):
        if self.overlay_mode and not self.chat_display.winfo_viewable():
            return
            
        timestamp = datetime.now().strftime("%H:%M:%S")
        username_tag = f"{platform}_username"
        
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, f"[{timestamp}] ", "timestamp")
        self.chat_display.insert(tk.END, f"{username}: ", username_tag)
        self.chat_display.insert(tk.END, f"{message}\n", "message")
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)
        
    def add_system_message(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, f"[{timestamp}] ", "timestamp")
        self.chat_display.insert(tk.END, f"{message}\n", "system")
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)
        
    def load_settings(self):
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r') as f:
                    settings = json.load(f)
                    
                self.twitch_token = settings.get('twitch_token')
                self.twitch_channel_var.set(settings.get('twitch_channel', ''))
                self.youtube_input_var.set(settings.get('youtube_input', ''))
                self.youtube_api_key = settings.get('youtube_api_key')
                self.transparency_var.set(settings.get('transparency', 90))
                
        except Exception as e:
            self.add_system_message(f"Error loading settings: {e}")
            
    def save_settings(self):
        try:
            settings = {
                'twitch_token': self.twitch_token,
                'twitch_channel': self.twitch_channel_var.get(),
                'youtube_input': self.youtube_input_var.get(),
                'youtube_api_key': self.youtube_api_key,
                'transparency': self.transparency_var.get()
            }
            
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            self.add_system_message(f"Error saving settings: {e}")
            
    def prompt_twitch_token(self):
        token_dialog = tk.Toplevel(self.root)
        token_dialog.title("Twitch OAuth Token")
        token_dialog.resizable(False, False)
        token_dialog.configure(bg='#18181b')
        
        instructions = (
            "1. Visit twitchtokengenerator.com\n"
            "2. Click 'Generate Token'\n"
            "3. Copy the 'Access Token'\n"
            "4. Paste it below:\n\n"
            "Note: You only need to do this once unless the token gets reset."
        )
        tk.Label(token_dialog, text=instructions, bg='#18181b', fg='white',
                justify=tk.LEFT, font=('Comic Sans MS', 10)).pack(padx=10, pady=5)
        
        help_frame = tk.Frame(token_dialog, bg='#18181b')
        help_frame.pack(fill=tk.X, pady=(0, 10))
        tk.Label(help_frame, text="Need help?", bg='#18181b', fg='white', font=('Comic Sans MS', 9)).pack(side=tk.LEFT)
        help_link = tk.Label(help_frame, text="Open Token Generator", fg='#9147ff',
                           cursor="hand2", bg='#18181b', font=('Comic Sans MS', 9))
        help_link.pack(side=tk.LEFT)
        help_link.bind("<Button-1>", lambda e: webbrowser.open(TOKEN_HELP_URL))
        
        token_entry = tk.Entry(token_dialog, width=40, bg='#2d2d2d', fg='white',
                             insertbackground='white', font=('Comic Sans MS', 10))
        token_entry.pack(padx=10, pady=5)
        
        btn_frame = tk.Frame(token_dialog, bg='#18181b')
        btn_frame.pack(pady=(0, 10))
        
        def on_submit():
            token = token_entry.get().strip()
            if token:
                if not token.startswith('oauth:'):
                    token = 'oauth:' + token
                self.twitch_token = token
                self.save_settings()
                token_dialog.destroy()
                return True
            return False
            
        tk.Button(btn_frame, text="Submit", bg='#9147ff', fg='white',
                 command=on_submit, font=('Comic Sans MS', 10)).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Cancel", bg='#ff4444', fg='white',
                 command=token_dialog.destroy, font=('Comic Sans MS', 10)).pack(side=tk.LEFT, padx=5)
        
        token_dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - token_dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - token_dialog.winfo_height()) // 2
        token_dialog.geometry(f"+{x}+{y}")
        
        self.root.wait_window(token_dialog)
        return self.twitch_token is not None
        
    def toggle_connection(self, platform):
        if platform == 'twitch':
            if not self.connected_services['twitch']:
                self.connect_twitch()
            else:
                self.disconnect_twitch()
        elif platform == 'youtube':
            if not self.connected_services['youtube']:
                self.connect_youtube()
            else:
                self.disconnect_youtube()
                
    def connect_twitch(self):
        if not self.twitch_token:
            if not self.prompt_twitch_token():
                return
                
        self.twitch_channel = self.twitch_channel_var.get().strip()
        if not self.twitch_channel:
            messagebox.showerror("Error", "Please enter a Twitch channel name")
            return
            
        try:
            context = ssl.create_default_context()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.twitch_sock = context.wrap_socket(sock, server_hostname=TWITCH_SERVER)
            self.twitch_sock.connect((TWITCH_SERVER, TWITCH_PORT))
            
            commands = [
                f"PASS {self.twitch_token}",
                "NICK justinfan12345",
                "CAP REQ :twitch.tv/tags twitch.tv/commands",
                f"JOIN #{self.twitch_channel}"
            ]
            
            for cmd in commands:
                self.twitch_sock.send(f"{cmd}\r\n".encode('utf-8'))
                
            self.connected_services['twitch'] = True
            self.twitch_connect_btn.config(text="Disconnect", bg='#ff4444')
            self.update_status()
            self.add_system_message(f"Connected to Twitch channel #{self.twitch_channel}")
            
            thread = threading.Thread(target=self.twitch_chat_listener, daemon=True)
            thread.start()
            self.chat_threads.append(thread)
            
        except Exception as e:
            self.add_system_message(f"Twitch connection error: {e}")
            
    def connect_youtube(self):
        youtube_input = self.youtube_input_var.get().strip()
        if not youtube_input:
            messagebox.showerror("Error", "Please enter a YouTube channel name, video ID, or URL")
            return
            
        try:
            video_id = self.extract_video_id_from_url(youtube_input)
            
            if not video_id:
                if len(youtube_input) == 11 and not youtube_input.startswith('@'):
                    video_id = youtube_input
                else:
                    self.add_system_message("Searching for live stream...")
                    video_id = self.get_live_video_from_channel(youtube_input)
                    
                    if not video_id:
                        self.add_system_message("No live stream found. Please try a video ID or URL.")
                        return
                        
            self.youtube_video_id = video_id
            self.youtube_chat = pytchat.create(video_id=video_id)
            
            self.connected_services['youtube'] = True
            self.youtube_connect_btn.config(text="Disconnect", bg='#ff4444')
            self.update_status()
            self.add_system_message(f"Connected to YouTube video {video_id}")
            
            thread = threading.Thread(target=self.youtube_chat_listener, daemon=True)
            thread.start()
            self.chat_threads.append(thread)
            
        except Exception as e:
            self.add_system_message(f"YouTube connection error: {e}")
            
    def disconnect_twitch(self):
        try:
            if self.twitch_sock:
                self.twitch_sock.close()
                
            self.connected_services['twitch'] = False
            self.twitch_connect_btn.config(text="Connect", bg='#9147ff')
            self.update_status()
            self.add_system_message("Disconnected from Twitch")
            
        except Exception as e:
            self.add_system_message(f"Twitch disconnect error: {e}")
            
    def disconnect_youtube(self):
        try:
            if self.youtube_chat:
                self.youtube_chat.terminate()
                
            self.connected_services['youtube'] = False
            self.youtube_connect_btn.config(text="Connect", bg='#ff0000')
            self.update_status()
            self.add_system_message("Disconnected from YouTube")
            
        except Exception as e:
            self.add_system_message(f"YouTube disconnect error: {e}")
            
    def update_status(self):
        status = []
        if self.connected_services['twitch']:
            status.append(f"Twitch: #{self.twitch_channel}")
        if self.connected_services['youtube']:
            status.append(f"YouTube: {self.youtube_video_id}")
            
        if not status:
            self.status_var.set("Disconnected from both services")
        else:
            self.status_var.set(" | ".join(status))
            
    def twitch_chat_listener(self):
        while self.connected_services['twitch']:
            try:
                resp = self.twitch_sock.recv(2048).decode('utf-8')
                
                if not resp:
                    self.root.after(0, self.disconnect_twitch)
                    break
                    
                if resp.startswith('PING'):
                    self.twitch_sock.send("PONG :tmi.twitch.tv\r\n".encode('utf-8'))
                else:
                    for line in resp.split('\r\n'):
                        if not line:
                            continue
                            
                        username, message, _ = self.parse_twitch_message(line)
                        if username and message:
                            self.root.after(0, self.add_message, 'twitch', username, message)
                            
            except Exception as e:
                self.root.after(0, self.add_system_message, f"Twitch chat error: {e}")
                self.root.after(0, self.disconnect_twitch)
                break
                
    def youtube_chat_listener(self):
        while self.connected_services['youtube'] and self.youtube_chat.is_alive():
            try:
                for c in self.youtube_chat.get().sync_items():
                    self.root.after(0, self.add_message, 'youtube', c.author.name, c.message)
                    
            except Exception as e:
                self.root.after(0, self.add_system_message, f"YouTube chat error: {e}")
                self.root.after(0, self.disconnect_youtube)
                break
                
    def parse_twitch_message(self, irc_message):
        match = re.match(r'^@([^ ]+) :([^!]+)!.* PRIVMSG #[^ ]+ :(.*)', irc_message)
        if match:
            tags = match.group(1)
            username = match.group(2)
            message = match.group(3)
            
            color = None
            for tag in tags.split(';'):
                if tag.startswith('color='):
                    color_value = tag.split('=')[1]
                    if color_value:
                        color = f'#{color_value}' if not color_value.startswith('#') else color_value
            
            return username, message, color
            
        match = re.match(r'^:([^!]+)!.* PRIVMSG #[^ ]+ :(.*)', irc_message)
        if match:
            username = match.group(1)
            message = match.group(2)
            return username, message, None
            
        return None, None, None
        
    def on_closing(self):
        self.save_settings()
        if self.connected_services['twitch']:
            self.disconnect_twitch()
        if self.connected_services['youtube']:
            self.disconnect_youtube()
        self.root.destroy()
        
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    try:
        import pytchat
        import requests
    except ImportError:
        import subprocess
        import sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pytchat", "requests"])
        import pytchat
        import requests
        
    app = MultiPlatformChat()
    app.run()