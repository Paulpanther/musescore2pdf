# This script runs continuously in a directory and looks for updates on musescore files in it.
# When it finds a new/updated file, it generates new pdfs into its pdf folder
# Musescore files are compared using hashes and stored in a sqlite DB


from argparse import ArgumentParser
from time import sleep
import os
import re
import subprocess
import sqlite3
import hashlib

root: str
scan_interval_seconds: int
ms: str

conn = sqlite3.connect("files.db")

def main():
    try:
        init_db()

        while True:
            scan_directories()
            sleep(scan_interval_seconds)
    except KeyboardInterrupt:
        conn.close()
        return


def scan_directories():
    ms_files = [os.path.join(dp, f) for dp, dn, filenames in os.walk(root) for f in filenames if os.path.splitext(f)[1] == '.mscz']
    print(f"Scanning found {len(ms_files)} musescore file(s)")

    for ms_file in ms_files:
        song_dir = os.path.dirname(ms_file)
        pdf_folders = [folder for dp, folders, _ in os.walk(song_dir) for folder in folders if re.match(r'^pdfs?$', folder)]
        force = False

        if len(pdf_folders) == 0:
            pdf_folder = os.path.join(song_dir, 'pdf')
            os.mkdir(pdf_folder)
            force = True  # pdf folder is empty so we must create new files
            print(f'Generated pdf folder in {song_dir}')
        else:
            pdf_folder = os.path.join(song_dir, pdf_folders[0])

        if len(pdf_folders) > 1:
            print(f'Found more than one pdf folder for song {song_dir}: {pdf_folders}. You should have only one folder. Will use {pdf_folders[0]}.')

        process_song(ms_file, pdf_folder, force)


def process_song(ms_file: str, pdf_folder: str, force: bool = False):
    if needs_update(ms_file) or force:  # check needs_update before 'force' as needs_update has side effects that mus be run
        with BatchConfig(ms_file, pdf_folder) as config:
            print(f'Generating parts for {ms_file}')
            subprocess.run([ms, '-j', config.file_name])


def sha256sum(filename):
    h  = hashlib.sha256()
    b  = bytearray(128*1024)
    mv = memoryview(b)
    with open(filename, 'rb', buffering=0) as f:
        while n := f.readinto(mv):
            h.update(mv[:n])
    return h.hexdigest()


def needs_update(ms_file: str) -> bool:
    hash = sha256sum(ms_file)

    cur = conn.cursor()
    cur.execute(f'SELECT hash FROM files WHERE path = "{ms_file}"')
    res = cur.fetchone()

    if res is None:
        cur.execute(f'INSERT INTO files (path, hash) VALUES ("{ms_file}", "{hash}")')
        conn.commit()
        return True
    if res[0] != hash:
        cur.execute(f'UPDATE files SET hash = "{hash}" WHERE path = "{ms_file}"')
        conn.commit()
        return True
    return False


def init_db():
    cur = conn.cursor()
    cur.execute("""
        create table if not exists files(
            path TEXT not null
                constraint files_pk
                    unique,
            hash TEXT not null
        );
    """)
    conn.commit()
    print('Initialized DB')


class BatchConfig:
    file_name = 'config.json'

    def __init__(self, ms_file: str, pdf_folder: str):
        self.ms_file = ms_file
        self.pdf_folder = pdf_folder

    def __enter__(self):
        with open(self.file_name, 'w') as file:
            song_name = os.path.splitext(os.path.basename(self.ms_file))[0]
            file.write(f'[{{"in": "{self.ms_file}","out": [["{os.path.join(self.pdf_folder, song_name)}-", ".pdf"]]}}]')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        os.remove(self.file_name)


if __name__ == '__main__':
    parser = ArgumentParser(
        prog='musescore2pdf',
        description='Watches a directory and converts musescore files in it to PDFs')
    parser.add_argument('root')
    parser.add_argument('-s', '--scan-interval-seconds', default='5', type=int)
    parser.add_argument('-ms', '--musescore', default='mscore')
    args = parser.parse_args()

    root = args.root
    scan_interval_seconds = args.scan_interval_seconds
    ms = args.musescore

    print(f'Started with params root={root}, scan_interval={scan_interval_seconds}s, ms={ms}')

    main()