import sys
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube"]

def main():
    if len(sys.argv) != 2:
        print("Usage: python auth_youtube.py client_secret.json")
        raise SystemExit(2)

    flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], SCOPES)
    credentials = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )

    print("\n=== COPY THESE INTO GITHUB ACTIONS SECRETS ===")
    print("YOUTUBE_CLIENT_ID=" + str(credentials.client_id))
    print("YOUTUBE_CLIENT_SECRET=" + str(credentials.client_secret))
    print("YOUTUBE_REFRESH_TOKEN=" + str(credentials.refresh_token))
    print("\nKeep these values private. Do not commit them.")

if __name__ == "__main__":
    main()
