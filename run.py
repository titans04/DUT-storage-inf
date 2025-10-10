from app import create_app

# Create the Flask app instance
app = create_app()

if __name__ == '__main__':
    # Run the app in debug mode
    # In a production environment, you would use a proper WSGI server like Gunicorn or uWSGI
    app.run(debug=True)
