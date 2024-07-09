# injusticejudge server

This is a simple [Quart](https://github.com/pallets/quart) server that accepts replay URLs and outputs a list of injustices.

## Usage

First populate `config.env` using the example template `config.template.env`.

Then run: `python main.py`

Once the server is up, you can query it using something like the following:

    curl -d '{"link": "https://mahjongsoul.game.yo-star.com/?paipu=231007-a7e3f77c-5290-4260-9605-fd1221d9ecc1_a823629735"}' -H "Content-Type: application/json" "http://127.0.0.1:5000/injustice"
