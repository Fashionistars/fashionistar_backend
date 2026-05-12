# chat/consumers.py

import json
import base64
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Message
from django.contrib.auth.models import User
from cryptography.fernet import Fernet
from django.conf import settings

# Generate a key for encryption and decryption
base_key = settings.SECRET_KEY.encode().ljust(32, b'\0')[:32]
cipher_suite = Fernet(base64.urlsafe_b64encode(base_key))


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        self.room_name = f'private_{self.user.id}'
        self.room_group_name = f'chat_{self.room_name}'

        try:
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            await self.accept()
        except Exception as e:
            await self.close()
            print(f"Error during connection: {e}")

    async def disconnect(self, close_code):
        try:
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
        except Exception as e:
            print(f"Error during disconnection: {e}")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message = data.get('message', '')
            recipient_id = data['recipient_id']
            files = data.get('files', None)

            recipient = await database_sync_to_async(User.objects.get)(id=recipient_id)

            # Encrypt the message
            encrypted_message = cipher_suite.encrypt(message.encode()).decode()

            # Save the message to the database
            msg_instance = await database_sync_to_async(Message.objects.create)(
                sender=self.user,
                recipient=recipient,
                message=encrypted_message
            )

            if files:
                for file in files:
                    # Assuming files are uploaded in base64 format
                    msg_instance.files.save(file['name'], base64.b64decode(file['content']))

            recipient_room_name = f'private_{recipient.id}'
            await self.channel_layer.group_send(
                f'chat_{recipient_room_name}',
                {
                    'type': 'chat_message',
                    'message': encrypted_message,
                    'sender': self.user.username,
                    'recipient': recipient.username,
                    'files': [{'name': file['name'], 'content': file['content']} for file in files] if files else None
                }
            )
        except User.DoesNotExist:
            await self.send(text_data=json.dumps({
                'error': 'Recipient does not exist.'
            }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                'error': str(e)
            }))

    async def chat_message(self, event):
        try:
            message = event['message']
            sender = event['sender']
            recipient = event['recipient']
            files = event.get('files', None)

            # Decrypt the message
            decrypted_message = cipher_suite.decrypt(message.encode()).decode()

            response_data = {
                'message': decrypted_message,
                'sender': sender,
                'recipient': recipient
            }

            if files:
                response_data['files'] = files

            await self.send(text_data=json.dumps(response_data))
        except Exception as e:
            print(f"Error sending message: {e}")
