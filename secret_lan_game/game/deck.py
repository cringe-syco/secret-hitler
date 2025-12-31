import random

class PolicyDeck:
    def __init__(self):
        self.deck = ["L"] * 6 + ["F"] * 11
        self.discard = []
        random.shuffle(self.deck)

    def draw(self, n=3):
        if len(self.deck) < n:
            self.deck.extend(self.discard)
            self.discard.clear()
            random.shuffle(self.deck)
        cards = self.deck[:n]
        self.deck = self.deck[n:]
        return cards

    def discard_card(self, card):
        self.discard.append(card)
