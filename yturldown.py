import os
import sys
import threading
import customtkinter as ctk
from tkinter import messagebox
import yt_dlp
import time
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- FUNGSI SAKTI UNTUK EXE ---
def resource_path(relative_path):
    """ Mengarahkan path ke folder sementara jika berjalan sebagai EXE """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class YtDriveApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("YouTube to Drive Pro - Portable Edition")
        self.geometry("600x550")

        # Path file penting (Otomatis deteksi dalam EXE)
        self.creds_path = resource_path("credentials.json")
        self.ffmpeg_path = resource_path("bin") # Folder bin berisi ffmpeg.exe
        
        self.SCOPES = ['https://www.googleapis.com/auth/drive.file']
        self.drive_service = None

        # UI
        self.setup_ui()

    def setup_ui(self):
        self.label = ctk.CTkLabel(self, text="🚀 YouTube to Drive Pro", font=("Roboto", 24, "bold"))
        self.label.pack(pady=20)

        self.url_entry = ctk.CTkEntry(self, placeholder_text="Paste Link YouTube di sini...", width=480, height=35)
        self.url_entry.pack(pady=10)

        self.btn_fetch = ctk.CTkButton(self, text="Cek Kualitas Video", command=self.start_fetch_thread)
        self.btn_fetch.pack(pady=10)

        self.status_label = ctk.CTkLabel(self, text="Status: Siap", text_color="gray")
        self.status_label.pack(pady=5)

        self.option_menu = ctk.CTkOptionMenu(self, values=["Cek video dulu..."], width=300)
        self.option_menu.pack(pady=15)

        self.progress_label = ctk.CTkLabel(self, text="0%", font=("Roboto", 12))
        self.progress_label.pack()

        self.progress_bar = ctk.CTkProgressBar(self, width=500)
        self.progress_bar.set(0)
        self.progress_bar.pack(pady=5)

        self.btn_download = ctk.CTkButton(self, text="Download & Upload ke Drive", 
                                         state="disabled", fg_color="#2ecc71", 
                                         hover_color="#27ae60", command=self.start_download_thread)
        self.btn_download.pack(pady=25)

    def get_drive_service(self):
        creds = None
        # Token disimpan di folder yang sama dengan EXE
        token_path = 'token.json' 
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, self.SCOPES)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.creds_path):
                    messagebox.showerror("Error", f"File {self.creds_path} tidak ditemukan!")
                    return None
                flow = InstalledAppFlow.from_client_secrets_file(self.creds_path, self.SCOPES)
                creds = flow.run_local_server(port=0)
            with open(token_path, 'w') as token:
                token.write(creds.to_json())
        return build('drive', 'v3', credentials=creds)

    def start_fetch_thread(self):
        threading.Thread(target=self.fetch_info, daemon=True).start()

    def fetch_info(self):
        url = self.url_entry.get()
        if not url: return
        self.btn_fetch.configure(state="disabled")
        self.status_label.configure(text="Mengambil data...", text_color="orange")
        
        try:
            ydl_opts = {'quiet': True, 'nocheckcertificate': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                self.formats_data = []
                display_options = []
                seen_res = set()

                for f in sorted(info['formats'], key=lambda x: x.get('height') or 0, reverse=True):
                    h = f.get('height')
                    if h and h not in seen_res:
                        size = (f.get('filesize') or f.get('filesize_approx') or 0) / 1e6
                        self.formats_data.append({'id': f['format_id'], 'res': h})
                        display_options.append(f"{h}p - {size:.1f} MB")
                        seen_res.add(h)

                self.option_menu.configure(values=display_options)
                self.option_menu.set(display_options[0])
                self.btn_download.configure(state="normal")
                self.status_label.configure(text=f"Ready: {info['title'][:40]}...", text_color="white")
        except Exception as e:
            messagebox.showerror("Error", f"Koneksi gagal: {e}")
        finally:
            self.btn_fetch.configure(state="normal")

    def start_download_thread(self):
        threading.Thread(target=self.process_task, daemon=True).start()

    def process_task(self):
        url = self.url_entry.get()
        choice = self.option_menu.get()
        selected_id = self.formats_data[self.option_menu._values.index(choice)]['id']

        self.btn_download.configure(state="disabled")
        save_folder = "temp_downloads"
        if not os.path.exists(save_folder): os.makedirs(save_folder)

        def progress_hook(d):
            if d['status'] == 'downloading':
                p = d.get('_percent_str', '0%').replace('%','')
                self.progress_bar.set(float(p)/100)
                self.progress_label.configure(text=f"Downloading: {p}%")

        try:
            ydl_opts = {
                'format': f'{selected_id}+bestaudio/best',
                'outtmpl': os.path.join(save_folder, '%(title)s.%(ext)s'),
                'merge_output_format': 'mp4',
                'ffmpeg_location': self.ffmpeg_path, # POINT PENTING
                'progress_hooks': [progress_hook],
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=True)
                file_path = ydl.prepare_filename(info_dict)
                if not os.path.exists(file_path):
                    file_path = file_path.rsplit('.', 1)[0] + ".mp4"

            self.status_label.configure(text="Mengunggah ke Drive...", text_color="green")
            if not self.drive_service: self.drive_service = self.get_drive_service()

            media = MediaFileUpload(file_path, resumable=True)
            request = self.drive_service.files().create(
                body={'name': os.path.basename(file_path)}, 
                media_body=media, fields='id'
            )
            
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    self.progress_bar.set(status.progress())
                    self.progress_label.configure(text=f"Uploading: {int(status.progress()*100)}%")
            
            messagebox.showinfo("Sukses", "Video sudah masuk ke Drive!")
            time.sleep(2)
            os.remove(file_path)
            self.status_label.configure(text="Siap", text_color="gray")

        except Exception as e:
            messagebox.showerror("Error", str(e))
        finally:
            self.btn_download.configure(state="normal")
            self.progress_bar.set(0)
            self.progress_label.configure(text="0%")

if __name__ == "__main__":
    app = YtDriveApp()
    app.mainloop()