class MentatRunner:
    def __init__(self):
        pass
    
    def get_response(self, data: str):
        return f'Responding to {data}'
    
    def interrupt(self):
        return 'Interrupting'
    
    def restart(self):
        return 'Restarting'