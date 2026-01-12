import hashlib
import json
from time import time
from firebase_config import get_db

class Blockchain:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Blockchain, cls).__new__(cls)
            cls._instance.db = get_db()
            cls._instance.chain_collection = cls._instance.db.collection('blockchain')
            cls._instance.chain = cls._instance.load_chain()
            if not cls._instance.chain:
                # Create the genesis block if the chain is empty
                cls._instance.new_block(previous_hash='1', proof=100)
        return cls._instance

    def load_chain(self):
        """Loads the blockchain from Firestore, ordered by index."""
        try:
            docs = self.chain_collection.order_by('index').stream()
            chain = [doc.to_dict() for doc in docs]
            return chain
        except Exception as e:
            print(f"Could not load blockchain from Firestore: {e}")
            return []

    def new_block(self, proof, previous_hash=None):
        """
        Creates a new block and adds it to the chain and Firestore.
        :param proof: The proof given by the Proof of Work algorithm
        :param previous_hash: (Optional) Hash of the previous block
        :return: New Block
        """
        block = {
            'index': len(self.chain) + 1,
            'timestamp': time(),
            'transactions': [], # In this app, a transaction is adding a question
            'proof': proof,
            'previous_hash': previous_hash or self.hash(self.chain[-1]),
        }
        # Add the block to the in-memory chain and then to Firestore
        self.chain.append(block)
        self.chain_collection.document(str(block['index'])).set(block)
        return block

    def new_transaction(self, question_id, question_text, bloom_level):
        """
        Adds a new transaction (a question record) to the current block.
        :return: The index of the block that will hold this transaction
        """
        if not self.chain:
            return None
            
        transaction_data = {
            'question_id': question_id,
            'question_text': question_text,
            'bloom_level': bloom_level,
            'timestamp': time()
        }
        
        # Get the latest block and add the transaction
        last_block_index = self.chain[-1]['index']
        last_block_doc = self.chain_collection.document(str(last_block_index))
        
        # Firestore update: add to the 'transactions' array
        current_transactions = self.chain[-1].get('transactions', [])
        current_transactions.append(transaction_data)
        self.chain[-1]['transactions'] = current_transactions
        
        last_block_doc.update({'transactions': current_transactions})

        return last_block_index

    @staticmethod
    def hash(block):
        """
        Creates a SHA-256 hash of a Block.
        :param block: Block
        :return: <str>
        """
        # We must make sure that the Dictionary is Ordered, or we'll have inconsistent hashes
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def last_block(self):
        """Returns the last block in the chain."""
        return self.chain[-1] if self.chain else None

    def proof_of_work(self, last_proof):
        """
        Simple Proof of Work Algorithm:
         - Find a number 'proof' such that hash(last_proof, proof) contains leading 4 zeroes.
        """
        proof = 0
        while self.valid_proof(last_proof, proof) is False:
            proof += 1
        return proof

    @staticmethod
    def valid_proof(last_proof, proof):
        """
        Validates the proof: Does hash(last_proof, proof) contain 4 leading zeroes?
        """
        guess = f'{last_proof}{proof}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"

    def is_chain_valid(self):
        """
        Determine if the stored blockchain is valid by checking hashes.
        """
        # Reload the chain from Firestore to ensure we have the latest state
        self.chain = self.load_chain()
        
        for i in range(1, len(self.chain)):
            current_block = self.chain[i]
            previous_block = self.chain[i-1]

            # Check if the hash of the block is correct
            if current_block['previous_hash'] != self.hash(previous_block):
                print(f"Chain invalid: Hash mismatch at block {current_block['index']}")
                return False
            
            # Check if the proof of work is correct
            if not self.valid_proof(previous_block['proof'], current_block['proof']):
                print(f"Chain invalid: Proof of work incorrect at block {current_block['index']}")
                return False
        
        return True

