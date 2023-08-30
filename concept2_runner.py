import subprocess

class Runner:
    def __init__(self):
        self.process = subprocess.Popen(["python3", "concept2.py", "-i", "vscode"],
                                        stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE,
                                        text=True)
        self.get_output()
        
    def user_input(self, input_str):
        self.process.stdin.write(input_str + '\n')
        self.process.stdin.flush()
        
    def get_output(self):
        try:
            while True:
                response = self.process.stdout.readline().strip()
                if not response:
                    break
                elif response == '@@user_input':
                    break
                else:
                    print(response)
        except KeyboardInterrupt:
            # Forward keyboardInterrupt to the subprocess
            # This isn't working quite right, but it's a stand-in for calling 'interrupt'.
            self.process.send_signal(2)
            self.get_output()

    def get_response(self, prompt):
        self.user_input(prompt)
        self.get_output()

"""
Run this in a terminal, Jupyter, etc:
>>> from concept2_runner import Runner
>>> runner = Runner()
>>> runner.get_response('Hello')
"""