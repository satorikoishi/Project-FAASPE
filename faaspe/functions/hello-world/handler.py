def handler(event=None, context=None):
    print("PRINTED Hello from my serverless function!")
    return "RETURNED This is return hello-world"

handler()