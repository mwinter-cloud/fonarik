from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer, AsyncWebsocketConsumer
from channels.db import database_sync_to_async
import json
from .models import Message
from .serializer import MessageSerializer

class PostConsumer(WebsocketConsumer):
    def connect(self):
        self.room_group_name = 'main-room'

        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name,
            self.channel_name
        )
        self.accept()

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.room_group_name,
            self.channel_name
        )

    def receive(self, text_data):
        text_data_json = json.loads(text_data) 
        id = text_data_json['id']
        text = text_data_json['text']
        images = text_data_json['images']
        attachments = text_data_json['attachments']
        created_at = text_data_json['created_at']

        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'post',
                'id': id,
                'text': text,
                'images': images,
                'attachments': attachments,
                'created_at': created_at,
            }
        )

    def post(self, event):
        id = event['id']
        text = event['text']
        created_at = event['created_at']
        images = event['images']
        attachments = event['attachments']

        self.send(text_data=json.dumps({
            'id': id,
            'text': text,
            'images': images,
            'attachments': attachments,
            'created_at': created_at,
        }))

class CommentConsumer(WebsocketConsumer):
    def connect(self):
        self.post_id = self.scope['url_route']['kwargs']['post_id'] 
        self.room_group_name = f'comments_{self.post_id}'           

        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name,
            self.channel_name
        )
        self.accept()

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.room_group_name,
            self.channel_name
        )

    def receive(self, text_data):
        data = json.loads(text_data)

        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'comment',
                'id': data['id'],
                'text': data['text'],
                'author': data['author'],
                'created_at': data['created_at'],
            }
        )

    def comment(self, event):
        self.send(text_data=json.dumps({
            'id': event['id'],
            'text': event['text'],
            'author': event['author'],
            'created_at': event['created_at'],
        }))

class UserConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']
        if self.user.is_anonymous:
            await self.close()
            return

        self.user_id = self.user.id
        self.room_group_name = f'user-{self.user_id}'

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)

        text = data.get('text', '').strip()
        recipient_id = data.get('to')
        parent_message_id = data.get('parent_message') or 0

        if not text or not recipient_id:
            return

        message_obj = await self.save_message(
            text=text,
            recipient_id=recipient_id,
            parent_message_id=parent_message_id,
        )

        payload = await self.serialize_message(message_obj)
        payload['type'] = 'new_message'

        await self.channel_layer.group_send(
            f'user-{recipient_id}',
            {'type': 'message', 'payload': payload}
        )

    async def message(self, event):
        await self.send(text_data=json.dumps(event['payload']))

    @database_sync_to_async
    def save_message(self, text, recipient_id, parent_message_id):
        return Message.objects.create(
            text=text,
            author=self.user,
            to=recipient_id,
            parent_message=parent_message_id,
            read=False,
        )

    @database_sync_to_async
    def serialize_message(self, message):
        return MessageSerializer(message).data