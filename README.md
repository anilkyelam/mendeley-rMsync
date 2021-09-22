# Remarkable Support for Mendeley
This tool syncs PDFs from a folder in [Mendeley Reference Manager](https://www.mendeley.com/download-reference-manager/) with a folder in [Remarkable Cloud](https://my.remarkable.com) (which ultimately ends up in your tablet if it is connected). 

## What does it do, exactly?
It takes files in a specified folder in Mendeley and makes sure that it matches with a folder in Remarkable. Both folder names are hard-coded right now, feel free to change them locally before running the script. And make sure the folders actually exist in both places!

Note that Mendeley's folder provides the ground truth, so any files not in Mendeley will be removed from Remarkable. And naturally, any new files added to Mendeley will be sent to Remarkable. For existing files at both places, it syncs the latest copy (with annotations) from Remarkable to Mendeley.


## How to run
The sync is not automatic right now, you need to run this script (after the One-time Setup below) everytime you want to synchronize:
```
git clone https://github.com/anilkyelam/mendeley-rMsync
cd mendeley-rMsync
python3 sync.py
```


## One-time Setup
Okay it's not strictly one-time, you may need to refresh credentials once every few months. Here are the steps:

1. Install [Python 3.*](https://www.python.org/downloads/)
2. And [Pip3](https://pip.pypa.io/en/stable/installation/)
    ```
    python3 -m ensurepip --upgrade
    ```
3. Install Python libraries that help the tool talk to the Mendeley Cloud.
    ```
    pip3 install mendeley python-dotenv 
    (run with --user flag if permission denied)
    ```
4. Here's the complicated part: To talk to Mendeley, you also need to authorize the tool with a Mendeley access token. Here's how to get it: 

      a. Register an application with Mendeley, instructions [here](https://dev.mendeley.com/reference/topics/application_registration.html).
        This is what I see after registration: ![image](https://user-images.githubusercontent.com/19861675/134260395-9406b5d6-9ec0-454c-8fd7-13050375652a.png)
        
      b. Now you should have the id (MENDELEY_CLIENT_ID), secret (MENDELEY_CLIENT_SECRET) and redirect URI (MENDELEY_REDIRECT_URI). 
      We need one more value: the token (MENDELEY_OAUTH2_TOKEN_BASE64). There's a complicated workflow [here](https://dev.mendeley.com/reference/topics/authorization_auth_code.html) but I found it simpler to use the [mendeley-cli](https://github.com/shuichiro-makigaki/mendeley_cli) tool to get the token. You can find how to install the tool and get the token in the tool's README, but here's a quick preview:
      ```
      pip3 install mendeley-cli --user
      MENDELEY_CLIENT_ID=<...> MENDELEY_CLIENT_SECRET=<...> MENDELEY_REDIRECT_URI=<...> mendeley get token
      ```
      
      c. Save all these in a file named `.mendeley_config` in the same folder as `sync.py`.
      ```
      MENDELEY_CLIENT_ID=<...>
      MENDELEY_REDIRECT_URI=<...>
      MENDELEY_CLIENT_SECRET=<...>
      MENDELEY_OAUTH2_TOKEN_BASE64=<...>
      ```

5. Okay, almost there. Now we need to authorize the tool to talk to Remarkable Cloud. We'll use the [rmapi](https://github.com/juruen/rmapi/releases) tool: just download it, place the executable in our folder and run it once to setup and add your current device. 
    ```
    ./rmapi
    ```
   (On MacOS, you may need to [bypass security](https://support.apple.com/en-us/HT202491) for this tool as it is apparently unverified)

6. That's it! Now just run the script and watch as it syncs your files one by one.
    ```
    python3 sync.py
    ```
    You may need to refresh your local Mendeley client to see the annotations from Remarkable.
