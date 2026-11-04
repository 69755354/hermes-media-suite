"""Explicit synthetic receipt fixtures. Never imported by application code."""
from types import SimpleNamespace
import uuid
from winport.publish_exec import NullDriver

def proof(mid,attempt='attempt',creation='creation',video='video'):
    return {'source':'playwright_response','result':'SUCCESS','ok':True,
            'status':200,'status_code':0,'item_id':mid,'work_id':mid,
            'attempt_id':attempt,'creation_id':creation,'video_id':video}

class ReceiptDriver(NullDriver):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.upload_attempt=SimpleNamespace(attempt_id='fixture-'+uuid.uuid4().hex)
    def click_publish(self,plan):
        super().click_publish(plan)
        creation='fixture-'+uuid.uuid4().hex
        self.bind_submission(creation,'fixture-video')
        self.last_publish_evidence={'ok':True,'receipt':proof(self.platform_work_id,self.upload_attempt.attempt_id,creation,'fixture-video')}
