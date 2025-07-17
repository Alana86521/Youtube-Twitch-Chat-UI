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
from PIL import Image, ImageTk
import io

TWITCH_SERVER = 'irc.chat.twitch.tv'
TWITCH_PORT = 6697
TOKEN_HELP_URL = "https://twitchtokengenerator.com"
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
TWITCH_API_BASE = "https://api.twitch.tv/helix"

BADGE_BASE_URL = "https://static-cdn.jtvnw.net/badges/v1/"
GLOBAL_BADGES_URL = "https://badges.twitch.tv/v1/badges/global/display"
CHANNEL_BADGES_URL = "https://badges.twitch.tv/v1/badges/channels/{channel_id}/display"
EMOTE_BASE_URL = "https://static-cdn.jtvnw.net/emoticons/v2/"

def get_config_path():
    appdata = os.getenv('APPDATA')
    if appdata:
        config_dir = os.path.join(appdata, 'Chat')
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, 'config.json')
    return 'chat_settings.json'

SETTINGS_FILE = get_config_path()

class MultiPlatformChat:
    def __init__(self):
        self.root = tk.Tk()
        self.icon_images = {
            "broadcaster": ImageTk.PhotoImage(Image.open(io.BytesIO(requests.get("https://static-cdn.jtvnw.net/badges/v1/5527c58c-fb7d-422d-b71b-f309dcb85cc1/3").content)).resize((16, 16))),
            "moderator": ImageTk.PhotoImage(Image.open(io.BytesIO(requests.get("https://static-cdn.jtvnw.net/badges/v1/3267646d-33f0-4b17-b3df-f923a41db1d0/3").content)).resize((16, 16))),
            "vip": ImageTk.PhotoImage(Image.open(io.BytesIO(requests.get("https://static-cdn.jtvnw.net/badges/v1/b817aba4-fad8-49e2-b88a-7cc744dfa6ec/3").content)).resize((16, 16))),
            "subscriber": ImageTk.PhotoImage(Image.open(io.BytesIO(requests.get("https://static-cdn.jtvnw.net/badges/v1/5d9f2208-5dd8-11e7-8513-2ff4adfae661/3").content)).resize((16, 16))),
            "subtember": ImageTk.PhotoImage(Image.open(io.BytesIO(requests.get("https://static-cdn.jtvnw.net/badges/v1/4149750c-9582-4515-9e22-da7d5437643b/3").content)).resize((16, 16)))
        }


        self.root.title("Chat")
        self.root.geometry("500x700")
        self.root.configure(bg='#18181b')

        self.overlay_mode = False
        self.transparency = 0.9
        self.twitch_channel_id = None

        self.badge_cache = {}
        self.emote_cache = {}
        self.global_badges = {}
        self.channel_badges = {}

        self.create_ui()

        self.twitch_sock = None
        self.youtube_chat = None
        self.connected_services = {'twitch': False, 'youtube': False}
        self.chat_threads = []

        self.twitch_token = None
        self.twitch_channel = None
        self.youtube_video_id = None
        self.youtube_api_key = None

        self.load_settings()

    def create_ui(self):
        """Create all UI components"""
        self.create_header()
        self.create_chat_display()
        self.create_connection_controls()
        self.create_overlay_controls()

    def create_header(self):
        """Create the draggable header with controls"""
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
        """Create the main chat display area"""
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
        self.chat_display.tag_configure("donation", background="#ffd700", foreground="#000", font=('Comic Sans MS', 15, 'bold'))
        self.chat_display.tag_configure("highlight", background="#2a402a")
        self.chat_display.tag_configure("subscriber", foreground="#00ff00")
        self.chat_display.tag_configure("moderator", foreground="#00bfff")
        self.chat_display.tag_configure("vip", foreground="#ff69b4")
        self.chat_display.tag_configure("broadcaster", foreground="#ff0000")
        self.chat_display.tag_configure("bits", foreground="#ff4500")

    def create_connection_controls(self):
        """Create connection control panels"""
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
        tk.Label(status_frame, textvariable=self.status_var, bg='#18181b', fg='white',
                font=('Comic Sans MS', 8)).pack(side=tk.LEFT)

        tk.Label(status_frame, text="Get Twitch Token", bg='#18181b', fg='#9147ff',
                font=('Comic Sans MS', 8, 'underline'), cursor="hand2").pack(side=tk.RIGHT)
        status_frame.winfo_children()[-1].bind("<Button-1>", lambda e: webbrowser.open(TOKEN_HELP_URL))

    def create_overlay_controls(self):
        """Create overlay mode controls"""
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

    def load_badge_data(self):
        """Load global and channel badge data from Twitch API"""
        try:

            response = requests.get(GLOBAL_BADGES_URL)
            if response.status_code == 200:
                self.global_badges = response.json().get('badge_sets', {})
        except Exception as e:
            print(f"Error loading global badge data: {e}")

    def load_channel_badge_data(self, channel_id):
        """Load channel-specific badge data"""
        try:
            url = CHANNEL_BADGES_URL.format(channel_id=channel_id)
            response = requests.get(url)
            if response.status_code == 200:
                self.channel_badges = response.json().get('badge_sets', {})
        except Exception as e:
            print(f"Error loading channel badge data: {e}")

    def get_badge_url(self, badge_name, badge_version):
        """Get the URL for a badge image"""

        if badge_name in self.channel_badges:
            versions = self.channel_badges[badge_name].get('versions', {})
            if badge_version in versions:
                return versions[badge_version].get('image_url_1x')

        if badge_name in self.global_badges:
            versions = self.global_badges[badge_name].get('versions', {})
            if badge_version in versions:
                return versions[badge_version].get('image_url_1x')

        return None

    def load_badge_image(self, badge_name, badge_version):
        """Load a badge image from Twitch"""
        cache_key = f"{badge_name}_{badge_version}"
        if cache_key in self.badge_cache:
            return self.badge_cache[cache_key]

        badge_url = self.get_badge_url(badge_name, badge_version)
        if not badge_url:
            return None

        try:
            response = requests.get(badge_url)
            if response.status_code == 200:
                img_data = response.content
                img = Image.open(io.BytesIO(img_data))
                img = img.resize((18, 18), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self.badge_cache[cache_key] = photo
                return photo
        except Exception as e:
            print(f"Error loading badge image: {e}")

        return None

    def load_emote_image(self, emote_id):
        """Load an emote image from Twitch"""
        if emote_id in self.emote_cache:
            return self.emote_cache[emote_id]

        try:
            emote_url = f"{EMOTE_BASE_URL}{emote_id}/default/dark/1.0"
            response = requests.get(emote_url)
            if response.status_code == 200:
                img_data = response.content
                img = Image.open(io.BytesIO(img_data))
                img = img.resize((24, 24), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self.emote_cache[emote_id] = photo
                return photo
        except Exception as e:
            print(f"Error loading emote image: {e}")

        return None

    def add_message(self, platform, username, message, color=None, badges=None, is_donation=False, is_highlight=False, bits=0, emotes=None):
        if self.overlay_mode and not self.chat_display.winfo_viewable():
            return

        timestamp = datetime.now().strftime("%H:%M:%S")
        username_tag = f"{platform}_username"

        self.chat_display.config(state=tk.NORMAL)

        self.chat_display.insert(tk.END, f"[{timestamp}] ", "timestamp")

        inserted_icon = False

        if platform == 'twitch' and badges:
            priority = ["broadcaster", "moderator", "vip", "subscriber", "subtember"]
            seen = set()
            for badge_name, _ in badges:
                if badge_name in priority and badge_name in self.icon_images and badge_name not in seen:
                    self.chat_display.image_create(tk.END, image=self.icon_images[badge_name])
                    self.chat_display.insert(tk.END, " ")
                    seen.add(badge_name)
                    inserted_icon = True
                    break

        username_style = username_tag
        if platform == 'twitch':
            if any(badge[0] == 'broadcaster' for badge in badges or []):
                username_style = "broadcaster"
            elif any(badge[0] == 'moderator' for badge in badges or []):
                username_style = "moderator"
            elif any(badge[0] == 'vip' for badge in badges or []):
                username_style = "vip"
            elif any(badge[0] == 'subscriber' for badge in badges or []):
                username_style = "subscriber"
            elif any(badge[0] == 'premium' for badge in badges or []):  
                username_style = "vip" 

        icon_type = None
        if platform == 'twitch':
            if any(badge[0] == 'broadcaster' for badge in badges or []):
                icon_type = "broadcaster"
            elif any(badge[0] == 'moderator' for badge in badges or []):
                icon_type = "moderator"
            elif any(badge[0] == 'vip' for badge in badges or []):
                icon_type = "vip"
            elif any(badge[0] == 'subscriber' for badge in badges or []):
                icon_type = "subscriber"

        self.chat_display.insert(tk.END, f"{username}: ", username_style)

        message_style = "message"
        if is_donation:
            message_style = "donation"
            if bits > 0:
                message = f"Cheered {bits} bits: {message}"
        elif is_highlight:
            message_style = "highlight"

        if platform == 'twitch' and emotes:
            message_parts = []
            last_pos = 0
            text = message

            emote_positions = []
            for emote_id, positions in emotes:
                for pos in positions:
                    start, end = map(int, pos.split('-'))
                    emote_positions.append((start, end, emote_id))

            emote_positions.sort()

            for start, end, emote_id in emote_positions:
                if start > last_pos:
                    message_parts.append(text[last_pos:start])

                emote_img = self.load_emote_image(emote_id)
                if emote_img:
                    message_parts.append(emote_img)
                else:
                    message_parts.append(text[start:end+1])

                last_pos = end + 1

            if last_pos < len(text):
                message_parts.append(text[last_pos:])

            for part in message_parts:
                if isinstance(part, str):
                    self.chat_display.insert(tk.END, part, message_style)
                else:
                    self.chat_display.image_create(tk.END, image=part)
        else:
            self.chat_display.insert(tk.END, message, message_style)

        self.chat_display.insert(tk.END, "\n")
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)

    def add_system_message(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")

        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, f"[{timestamp}] ", "timestamp")
        self.chat_display.insert(tk.END, f"{message}\n", "system")
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)

    def get_twitch_channel_id(self, channel_name):
        """Get Twitch channel ID from login name"""
        try:
            headers = {
                'Authorization': f'Bearer {self.twitch_token}'
            }
            params = {'login': channel_name}
            response = requests.get(f"{TWITCH_API_BASE}/users", headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                if data.get('data'):
                    return data['data'][0]['id']
        except Exception as e:
            print(f"Error getting channel ID: {e}")
        return None

    def connect_twitch(self):
        if not self.twitch_token:
            if not self.prompt_twitch_token():
                return

        self.twitch_channel = self.twitch_channel_var.get().strip().lower()
        if not self.twitch_channel:
            messagebox.showerror("Error", "Please enter a Twitch channel name")
            return

        try:

            self.twitch_channel_id = self.get_twitch_channel_id(self.twitch_channel)
            if self.twitch_channel_id:
                self.load_channel_badge_data(self.twitch_channel_id)

            context = ssl.create_default_context()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.twitch_sock = context.wrap_socket(sock, server_hostname=TWITCH_SERVER)
            self.twitch_sock.connect((TWITCH_SERVER, TWITCH_PORT))

            commands = [
                f"PASS {self.twitch_token}",
                "NICK justinfan12345",
                "CAP REQ :twitch.tv/tags twitch.tv/commands twitch.tv/membership",
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

                        username, message, color, badges, is_donation, is_highlight, bits, emotes = self.parse_twitch_message(line)
                        if username and message:
                            self.root.after(0, self.add_message, 'twitch', username, message, color, badges, is_donation, is_highlight, bits, emotes)

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
        tags = {}
        username = None
        message = None
        color = None
        badges = []
        is_donation = False
        is_highlight = False
        bits = 0
        emotes = []

        if irc_message.startswith('@'):
            tag_part, irc_message = irc_message.split(' ', 1)
            for tag in tag_part[1:].split(';'):
                if '=' in tag:
                    key, value = tag.split('=', 1)
                    tags[key] = value

        privmsg_match = re.match(r':([^!]+)![^ ]+ PRIVMSG #[^ ]+ :(.*)', irc_message)
        if privmsg_match:
            username = privmsg_match.group(1)
            message = privmsg_match.group(2)

            is_donation = any(word in message.lower() for word in ['donated', 'donation', 'cheered'])
            is_highlight = 'msg-id=highlighted-message' in tags.get('flags', '')

            if 'bits' in tags:
                try:
                    bits = int(tags['bits'])
                    is_donation = True
                except:
                    pass

            color = tags.get('color')
            if color:
                color = f'#{color}' if not color.startswith('#') else color

            badge_info = tags.get('badges', '')
            if badge_info:
                for badge in badge_info.split(','):
                    badge_parts = badge.split('/', 1)
                    if len(badge_parts) == 2:
                        badge_name, badge_version = badge_parts
                        badges.append((badge_name, badge_version))

            emote_info = tags.get('emotes', '')
            if emote_info:
                for emote in emote_info.split('/'):
                    emote_parts = emote.split(':')
                    if len(emote_parts) >= 2:
                        emotes.append((emote_parts[0], emote_parts[1:]))

        return username, message, color, badges, is_donation, is_highlight, bits, emotes

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

    def extract_video_id_from_url(self, url):
        if 'youtube.com/watch' in url:
            parsed = urlparse(url)
            return parse_qs(parsed.query).get('v', [None])[0]
        elif 'youtu.be/' in url:
            return url.split('youtu.be/')[-1].split('?')[0]
        return None

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

    def on_closing(self):
        self.save_settings()
        if self.connected_services['twitch']:
            self.disconnect_twitch()
        if self.connected_services['youtube']:
            self.disconnect_youtube()
        self.root.destroy()

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()

if __name__ == "__main__":
    try:
        import pytchat
        import requests
        from PIL import Image, ImageTk
    except ImportError:
        import subprocess
        import sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pytchat", "requests", "pillow"])
        import pytchat
        import requests
        from PIL import Image, ImageTk

    app = MultiPlatformChat()
    app.run()
