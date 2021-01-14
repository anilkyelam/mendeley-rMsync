#
# Syncs a *top-level* folder on mendeley with a *top-level* folder 
# in remarkable tablet.
# 
#
# Prerequisites/Instructions:
# 1. Python3
# 2. pip install mendeley dotenv
# 3. Auth token for mendeley. This requires registering a oauth app 
#    with mendeley and acquiring an auth token, and saving all this 
#    info in .mendeley_config file in current dir or user home.
#    Reference: https://dev.mendeley.com/reference/topics/authorization_auth_code.html
# 4. Download rmapi and setup auth: https://github.com/juruen/rmapi/releases
#    Place the executable in the same folder. A python library would 
#    be more convenient ( https://rmapy.readthedocs.io/en/latest/) but 
#    it doesn't support export feature as of Jan 2021
# 5. Run "python sync.py"
#
# 
# Example workflow:
# When I add papers to folder named "Remarkable" on Mendeley, they 
# automatically appear on my remarkable once I run this script. The 
# same action would also sync any papers and associated annotations 
# already added in remarkable to mendeley i.e., highlights and notes 
# added in remarkable would appear on mendeley (after a mendeley sync).
# Furthermore, the papers removed from the mendeley folder would be 
# removed from remarkable with a latest version saved to trash folder 
# for recovering any missed annotations later.
# 
#
# Disclaimer:
# Documents synced with remarkable MAY lose *all* previously attached 
# files and annotations. It is expected that all further work 
# on that document will be done in remarkable. It will stop getting 
# affected as soon as the document is moved out of the remarkabe folder.
# Not surprisingly, this is the next big TODO i.e., how to sync documents 
# without losing mendeley annotations and notes.
#


from pathlib import Path
from pprint import pprint
import shutil
import logging
import os
import http
import http.server
import webbrowser
import base64
from urllib import parse
import json
import subprocess
import uuid

from mendeley import Mendeley, MendeleyAuthorizationCodeAuthenticator
from mendeley.session import MendeleySession
from mendeley.auth import MendeleyAuthorizationCodeTokenRefresher
from mendeley.exception import MendeleyApiException, MendeleyException
from dotenv import load_dotenv


# Constants
REMARKABLE_FOLDER_IN_MENDELEY = "Remarkable"
MENDELEY_FOLDER_IN_REMARKABLE = "Mendeley"


# Loads env from either of these paths
load_dotenv(Path('~').expanduser()/'.mendeley_config')
load_dotenv(Path()/'.mendeley_config')


mendeley_client = Mendeley(int(os.getenv('MENDELEY_CLIENT_ID')),
                            os.getenv('MENDELEY_CLIENT_SECRET'),
                            redirect_uri=os.getenv('MENDELEY_REDIRECT_URI'))
mendeley_token_b64 = os.getenv('MENDELEY_OAUTH2_TOKEN_BASE64', None)


# Call back server for OAuth
callback_html = '''
<html>
<head>
  <title>Mendeley CLI</title>
</head>
<body>
Login succeeded. You can close this window or tab.<br />
Please follow messages in the terminal to save your token.
</body>
</html>
'''.encode()


class RH(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse.parse_qs(parse.urlparse(self.path).query)
        auth = mendeley_client.start_authorization_code_flow(query['state'][0])
        mendeley_session = auth.authenticate(f'{mendeley_client.redirect_uri}{self.path}')
        mendeley_token = json.dumps(mendeley_session.token)
        mendeley_token_b64 = base64.b64encode(mendeley_token.encode()).decode()
        self.send_response(http.HTTPStatus.OK)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(callback_html)
        print('Login succeeded.')
        print('Please set an environment variable MENDELEY_OAUTH2_TOKEN_BASE64 or add it to a config file:')
        print()
        print(f'MENDELEY_OAUTH2_TOKEN_BASE64={mendeley_token_b64}')
        print()

def get_token():
    """Login and get token"""
    # webbrowser.open(mendeley_client.start_authorization_code_flow().get_login_url())
    print("Open below URL in browser:")
    print(mendeley_client.start_authorization_code_flow().get_login_url())
    netloc = parse.urlparse(mendeley_client.redirect_uri)
    http.server.HTTPServer((netloc.hostname, netloc.port), RH).handle_request()

def get_session():
    if mendeley_token_b64 is None:
        raise MendeleyException('Login required. Please `mendeley get token` first.')
    else:
        mendeley_token = json.loads(base64.b64decode(mendeley_token_b64.encode()).decode())
        auth = MendeleyAuthorizationCodeAuthenticator(mendeley_client, None)
        mendeley_session = MendeleySession(auth.mendeley, token=mendeley_token, client=auth.client,
                                           refresher=MendeleyAuthorizationCodeTokenRefresher(auth))
    return mendeley_session


# Current allowable request range per page: [20, 500]
# Check limit parameter for apis at https://api.mendeley.com/apidocs/docs
MENDELEY_PAGINATION_LIMIT = 500

# Model for mendeley folder
# mendeley library doesn't provide "folders" natively; need to query using raw api
class Folder:
    """Object representing a folder in mendeley"""

    def __init__(self, id, name, parent_id):
        self.id = id
        self.name = name
        self.parent = parent_id

    # Reference: https://api.mendeley.com/apidocs/docs#!/folders/getDocumentsForFolder
    def documents(self, session):
        """Lists all documents in the folder"""
        document_ids = []
        FOLDERS_DOCS_REST_URI = "https://api.mendeley.com/folders/{}/documents?limit={}"
        uri = FOLDERS_DOCS_REST_URI.format(self.id, MENDELEY_PAGINATION_LIMIT)
        rsp = session.request("GET", uri)
        while True:
            # results may be returned in multiple pages
            for f in json.loads(rsp.content):
                document_ids.append(f["id"])
        
            # are there more pages to read?
            if "next" not in rsp.links:
                break
            rsp = session.request("GET", rsp.links["next"]["url"])

        # NOTE: If each get() makes a separate API request, it'll be a lot of requests 
        # if there are a lot of documents in the folder; mendeley may impose api request 
        # quotas but for now, tens of documents seems to be working fine. We may need to
        # move to documents.iter() and get them in big batches if we hit this limit.
        documents = [session.documents.get(id) for id in document_ids]
        return documents

    # Reference: https://api.mendeley.com/apidocs/docs#!/folders/getFolders
    def get_folders(session):
        """Lists <id,name> of all the user folders in mendeley"""
        folders = []
        FOLDERS_REST_URI = "https://api.mendeley.com/folders?limit={}"
        uri = FOLDERS_REST_URI.format(MENDELEY_PAGINATION_LIMIT)
        rsp = session.request("GET", uri)
        while True:
            # results may be returned in multiple pages
            for f in json.loads(rsp.content):
                parent_id = f["parent_id"] if "parent_id" in f else None
                folders.append(Folder(f["id"], f["name"], parent_id))
        
            # are there more pages to read?
            if "next" not in rsp.links:
                break
            rsp = session.request("GET", rsp.links["next"]["url"])
        return folders


# Python wrapper for rmapi
class RmApi:
    def __init__(self, exec_path = "./rmapi"):
        self.path = exec_path

    def _run(self, *args):
        args = (self.path, *args)
        popen = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        ret = popen.wait()
        output = popen.stdout.read()
        error = popen.stderr.read()
        if ret != 0:
            raise Exception("RmAPI {} command failed: {}".format(args, error))
        return output

    def subfolders(self, parent=None):
        out = self._run("ls") if not parent else self._run("ls", parent)
        # parse entries from rmapi output: this can be very flaky
        entries = out.decode('utf-8').split("\n")
        entries = [e.split("\t") for e in entries]
        return [e[1] for e in entries if e[0] == "[d]"]

    def files(self, parent=None):
        out = self._run("ls") if not parent else self._run("ls", parent)
        # parse entries from rmapi output: this can be very flaky
        entries = out.decode('utf-8').split("\n")
        entries = [e.split("\t") for e in entries]
        return [e[1] for e in entries if e[0] == "[f]"]

    def download(self, rfolder, rfile, outpath):
        """Download a single file from remarkable <rfolder/rfile> path exported with annotations"""
        rpath="{}/{}".format(rfolder, rfile)
        out = self._run("geta", "-a", rpath)
        localpath = "{}-annotations.pdf".format(rfile)      # the downloaded file format
        if not os.path.exists(localpath):
            raise Exception("File not downloaded from remarkable cloud: {}".format(rpath))
        shutil.move(localpath, outpath)
        os.remove("{}.zip".format(rfile))

    def upload(self, inpath, rfolder):
        """Upload a single local file to remarkable <rfolder>"""
        self._run("put", inpath, rfolder)

    def remove(self, rfolder, rfile):
        """Delete a single file on remarkable <rfolder>/<rfile>"""
        rpath="{}/{}".format(rfolder, rfile)
        self._run("rm", rpath)


def to_filename(text, nospaces=False):
    """Removes weird characters from a text to return a consistent name for file naming"""
    # add rules as we go
    text = text.replace(".", "")      # remove periods from title
    return text


# Main workflow
def main():
    # mendeley session
    session = get_session()
    
    # Find the remarkable folder in mendeley
    folders = Folder.get_folders(session)
    mfolder = next(filter(lambda f: f.name == REMARKABLE_FOLDER_IN_MENDELEY, folders), None)
    if not mfolder:
        print("Cannot find '{}' folder in mendeley. \nHere's the flattened list of folders: {}", 
            REMARKABLE_FOLDER_IN_MENDELEY, ", ".join([f.name for f in folders]))
        raise Exception("Cannot find remarkable folder in mendeley!")

    # Get documents
    mdocuments = mfolder.documents(session)
    mfiles = {"{}---{}".format(to_filename(m.title), m.id) : idx  
                for idx, m in enumerate(mdocuments)}      # all files names must be in this format

    # # See what files are present in the tablet
    rmapi = RmApi()
    topfolders = rmapi.subfolders()
    if MENDELEY_FOLDER_IN_REMARKABLE not in topfolders:
        print("Cannot find '{}' root-level folder in remarkable.".format(MENDELEY_FOLDER_IN_REMARKABLE))
        print("Create it if it does not exist, I won't.\nCurrent top-level folders: ", ", ".join(topfolders))
        raise Exception("Cannot find mendeley folder in remarkable!")

    rfiles = rmapi.files(MENDELEY_FOLDER_IN_REMARKABLE)
    # print(rfiles)
    
    # Get the diff b/w mendeley and remarkable
    m_and_r = [f for f in mfiles.keys() if f in rfiles]
    m_minus_r = [f for f in mfiles.keys() if f not in rfiles]
    r_minus_m = [f for f in rfiles if f not in mfiles.keys()]
    # print(m_and_r, m_minus_r, r_minus_m)

    # For documents in both, assume that remarkable has the updated file with annotations
    # mendeley annotations are saved separately from the file itself so replacing the file 
    # shouldn't affect the mendeley notes/comments.
    for doc in m_and_r:
        mdoc = mdocuments[mfiles[doc]]      
        # download from remarkable with annotations
        try:
            localpath = "{}.pdf".format(uuid.uuid4().hex)
            rmapi.download(MENDELEY_FOLDER_IN_REMARKABLE, doc, localpath)
        except Exception as ex:
            # Skip if the error is about not having any annotations at all
            if "Failed to generate annotations" in str(ex):
                print("Document skipped: {}. No annotations yet!".format(doc))
                continue
            raise
        # NOTE: remove *all* currently attached files in mendeley
        for file_ in mdoc.files.iter():
            file_.delete()
        mdoc.attach_file(localpath)
        os.remove(localpath)
        print("Document synced: {}".format(doc))

    
    # For documents in mendeley that are not in remarkable: add them to remarkable
    # NOTE: we only consider first of the attached files for the document
    for doc in m_minus_r:
        mdoc = mdocuments[mfiles[doc]]
        path = None
        for file_ in mdoc.files.iter():
            print(file_)
            path = file_.download(".")
            break
        if not path:
            print("WARNING! no files attached for document: {}".format(mdoc.title))
            continue
        properpath = "{}.pdf".format(doc)       # name in remarkable, proper format
        shutil.move(path, properpath)
        rmapi.upload(properpath, MENDELEY_FOLDER_IN_REMARKABLE)
        os.remove(properpath)
        print("Document added: {}".format(doc))
        

    # For documents in remarkable that are not in mendeley: remove them from remarkable,
    # mendeley will be the source of truth. Any annotations made in remarkable that were 
    # NOT previously synced will be lost.
    trash = "trash"
    if not os.path.exists(trash):   os.makedirs(trash)
    for doc in r_minus_m:
        # download from remarkable with annotations and save it to trash, just in case
        localpath = "{}.pdf".format(doc)
        trashpath = "{}/{}".format(trash, localpath)
        rmapi.download(MENDELEY_FOLDER_IN_REMARKABLE, doc, localpath)
        shutil.move(localpath, trashpath)
        # delete it from remarkable
        rmapi.remove(MENDELEY_FOLDER_IN_REMARKABLE, doc)
        print("Document removed: {}".format(doc))
        
    print("Sync complete! Refresh your mendeley and remarkable apps.")


if __name__=='__main__':
    main()
