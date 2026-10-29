import json
import os


class ContractClient:
    """
    Wrapper over the Smart Contract ABI, to gracefully bridge Python data to Solidity.

    The API of this class should match that of the smart contract.
    """

    CONTRACT_JSON_PATH = os.path.normpath(os.path.join(
        "..", "..", "build", "contracts", "Contributions.json"))

    def __init__(self,
                 web3,
                 account_idx=0
                 ):
        """
        web3: an instantiated web3 provider, such as `Web3(HTTPProvider("http://127.0.0.1:7545"))`
        """
        self._web3 = web3
        self._address = self._web3.eth.accounts[account_idx]
        self._web3.eth.defaultAccount = self._address
        self._contract = self._load_contract()
        self.contract_address = self._contract.address

    def owner(self):
        return self._contract.functions.owner().call()

    def tokens(self, address):
        return self._contract.functions.tokens(address).call()

    def totalTokens(self):
        return self._contract.functions.totalTokens().call()

    def balance(self, address):
        return self._contract.functions.balance(address).call()

    def transfer(self, amount):
        self._contract.functions.receive().transact({'value': amount})

    def giveTokens(self, recipient, num_tokens):
        self._contract.functions.giveTokens(
            recipient, num_tokens).transact()

    def _load_contract(self):
        with open(self.CONTRACT_JSON_PATH, encoding="utf-8-sig") as crt_json_file:
            crt_json = json.load(crt_json_file)
            abi = crt_json['abi']
            bytecode = crt_json['bytecode']

        configured_address = os.getenv("CONTRIBUTIONS_CONTRACT_ADDRESS")
        network_id = str(self._web3.net.version)
        deployed_network = crt_json.get("networks", {}).get(network_id, {})
        deployed_address = configured_address or deployed_network.get("address")

        if deployed_address:
            checksum_address = self._web3.toChecksumAddress(deployed_address)
            if self._web3.eth.getCode(checksum_address) not in (b"", "0x"):
                return self._web3.eth.contract(
                    address=checksum_address,
                    abi=abi
                )

        # Development fallback: deploy once when the artifact has no address for
        # the connected Ganache network. Set CONTRIBUTIONS_CONTRACT_ADDRESS in
        # shared environments to guarantee front-end/back-end consistency.
        Contributions = self._web3.eth.contract(
            abi=abi,
            bytecode=bytecode
        )
        tx_hash = Contributions.constructor().transact()
        tx_receipt = self._web3.eth.waitForTransactionReceipt(tx_hash)
        instance = self._web3.eth.contract(
            address=tx_receipt.contractAddress,
            abi=abi
        )
        return instance
