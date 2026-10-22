from app import create_app

app = create_app()

@app.context_processor
def inject_lang():
    from flask import request
    lang = request.args.get('lang', 'en')
    return dict(lang=lang)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
