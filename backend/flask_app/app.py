import ast
import hashlib
import os
from os import path

import joblib
import torch
import torch.optim as optim
from flask import Flask, Response, abort, json, request, send_from_directory
from flask_cors import CORS
from sklearn.model_selection import train_test_split
from werkzeug.utils import secure_filename
from web3 import HTTPProvider, Web3

import data_utils
import syft as sy
from contract_utils import ContractClient
from privacy_utils import summarize_compression, transform_state_update


hook = sy.TorchHook(torch)
app = Flask(__name__)
CORS(app)

BASE_DIR = path.dirname(path.abspath(__file__))
UPLOAD_FOLDER = path.join(BASE_DIR, "uploads")
ALLOWED_FILE = "net.py"
SAVED_MODEL_NAME = "model.pt"
MAX_MODEL_FILE_SIZE = 512 * 1024

EPOCHS = int(os.getenv("FL_EPOCHS", "2"))
BATCH_SIZE = int(os.getenv("FL_BATCH_SIZE", "8"))
LEARNING_RATE = float(os.getenv("FL_LEARNING_RATE", "0.01"))
NUMBER_OF_WORKERS = int(os.getenv("FL_WORKERS", "5"))
KEEP_RATIO = float(os.getenv("FL_KEEP_RATIO", "0.5"))
QUANTIZATION_BITS = int(os.getenv("FL_QUANTIZATION_BITS", "4"))
CLIP_NORM = float(os.getenv("FL_CLIP_NORM", "1.0"))
NOISE_MULTIPLIER = float(os.getenv("FL_NOISE_MULTIPLIER", "0.01"))
WEI_PER_UNIT_LOSS = int(float(os.getenv("WEI_PER_UNIT_LOSS", "1e18")))

LOSS_CRITERION = torch.nn.BCELoss()
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def init_syft_workers(eth_accounts):
    workers = data_utils.generate_virtual_workers(NUMBER_OF_WORKERS, hook)
    if len(eth_accounts) < NUMBER_OF_WORKERS + 1:
        raise RuntimeError(
            "Ganache needs at least {} accounts".format(NUMBER_OF_WORKERS + 1)
        )

    worker_accounts = {
        worker.id: eth_accounts[index + 1]
        for index, worker in enumerate(workers)
    }
    sy.VirtualWorker(hook, id="aggregator")

    frame = joblib.load(path.join(BASE_DIR, "Data.bin"))
    x_train, x_test, y_train, y_test = train_test_split(
        frame.drop(["ICU"], axis=1),
        frame["ICU"],
        test_size=0.2,
        random_state=101,
        stratify=frame["ICU"],
    )

    records, labels = data_utils.split_into_lists(x_train, y_train)
    records = data_utils.convert_to_tensors(records)
    federated_set = sy.BaseDataset(records, labels).federate(workers)
    train_loader = sy.FederatedDataLoader(
        federated_set,
        batch_size=BATCH_SIZE,
        shuffle=True,
    )

    test_records, test_labels = data_utils.split_into_lists(x_test, y_test)
    test_records = data_utils.convert_to_tensors(test_records)
    test_dataset = sy.BaseDataset(test_records, test_labels)
    test_loader = torch.utils.data.DataLoader(
        test_dataset,
        batch_size=BATCH_SIZE,
    )
    return workers, train_loader, test_loader, worker_accounts


def validate_model_source(filename):
    if path.getsize(filename) > MAX_MODEL_FILE_SIZE:
        raise ValueError("Model source exceeds the 512 KB limit")

    with open(filename, "r", encoding="utf-8") as source_file:
        source = source_file.read()

    tree = ast.parse(source)
    has_net_class = any(
        isinstance(node, ast.ClassDef) and node.name == "Net"
        for node in tree.body
    )
    if not has_net_class:
        raise ValueError("The uploaded source must define class Net")
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def load_model():
    # The uploaded file is validated and fingerprinted but deliberately not
    # executed. The interactive demo trains this audited server-side model.
    from net import Net
    return Net()


def clone_state(model):
    return {
        name: value.detach().clone()
        for name, value in model.state_dict().items()
    }


def merge_stats(target, update):
    for key in target:
        target[key] += update[key]


def test(model, loader, quiet=True):
    model.eval()
    total_loss = 0
    total_correct = 0
    total_predictions = 0
    with torch.no_grad():
        for data, target in loader:
            output = model(data.float())
            loss = LOSS_CRITERION(output, target.float()).item()
            total_loss += loss
            total_correct += (torch.round(output) == target).int().sum().item()
            total_predictions += len(target)

    mean_loss = total_loss / max(1, len(loader))
    accuracy = total_correct / max(1, total_predictions)
    if not quiet:
        print(
            "Test: Loss {:.6f}, Accuracy {}/{} ({:.2f}%)".format(
                mean_loss,
                total_correct,
                total_predictions,
                accuracy * 100,
            )
        )
    return mean_loss, accuracy


def train_epoch(model, train_loader, test_loader, optimizer, epoch):
    model.train()
    epoch_stats = {
        "original_bytes": 0,
        "compressed_bytes": 0,
        "nonzero": 0,
        "elements": 0,
    }

    for batch_index, (data, target) in enumerate(train_loader):
        test_loss_before, _ = test(model, test_loader)
        state_before = clone_state(model)

        model.send(data.location)
        optimizer.zero_grad()
        output = model(data.float())
        train_loss = LOSS_CRITERION(output, target.float())
        train_loss.backward()
        optimizer.step()
        model.get()

        protected_state, batch_stats = transform_state_update(
            state_before,
            clone_state(model),
            keep_ratio=KEEP_RATIO,
            quantization_bits=QUANTIZATION_BITS,
            clip_norm=CLIP_NORM,
            noise_multiplier=NOISE_MULTIPLIER,
        )
        model.load_state_dict(protected_state)
        merge_stats(epoch_stats, batch_stats)

        test_loss_after, _ = test(model, test_loader)
        tokens_earned = int(
            max(0, test_loss_before - test_loss_after) * WEI_PER_UNIT_LOSS
        )
        if tokens_earned:
            contract.giveTokens(
                worker_eth_accounts[data.location.id],
                tokens_earned,
            )

        if batch_index % 20 == 0:
            print(
                "Epoch {} [{}/{}] loss {:.6f}".format(
                    epoch,
                    batch_index * BATCH_SIZE,
                    len(train_loader) * BATCH_SIZE,
                    train_loss.get().item(),
                )
            )

    return epoch_stats


def train_model(model):
    optimizer = optim.SGD(model.parameters(), lr=LEARNING_RATE)
    run_stats = {
        "original_bytes": 0,
        "compressed_bytes": 0,
        "nonzero": 0,
        "elements": 0,
    }

    for epoch in range(1, EPOCHS + 1):
        epoch_stats = train_epoch(
            model,
            federated_train_loader,
            test_loader,
            optimizer,
            epoch,
        )
        merge_stats(run_stats, epoch_stats)

    test_loss, test_accuracy = test(model, test_loader, quiet=False)
    total_tokens = contract.totalTokens()
    contribution_rows = []

    for worker in workers:
        address = worker_eth_accounts[worker.id]
        tokens = contract.tokens(address)
        share = tokens / total_tokens if total_tokens else 0
        contribution_rows.append({
            "node": worker.id,
            "address": address,
            "tokens": tokens,
            "share": round(share, 6),
            "percent": round(share * 100, 2),
        })

    metrics = {
        "accuracy": round(test_accuracy, 6),
        "loss": round(test_loss, 6),
        "contributions": contribution_rows,
        "compression": summarize_compression(run_stats),
        "privacy": {
            "mechanism": "clipping + adaptive Gaussian perturbation",
            "clip_norm": CLIP_NORM,
            "noise_multiplier": NOISE_MULTIPLIER,
            "formal_dp_audited": False,
        },
        "training": {
            "workers": NUMBER_OF_WORKERS,
            "epochs": EPOCHS,
            "batch_size": BATCH_SIZE,
            "keep_ratio": KEEP_RATIO,
            "quantization_bits": QUANTIZATION_BITS,
        },
    }

    for index, row in enumerate(contribution_rows):
        metrics["contrib_{}".format(chr(ord("a") + index))] = row["share"]

    return model, metrics


@app.route("/api/status")
def system_status():
    return {
        "status": "ready",
        "workers": NUMBER_OF_WORKERS,
        "contract_address": contract.contract_address,
        "network_id": web3.eth.chainId,
        "privacy_pipeline": True,
        "ckks_experiment": "FLPyfhelin.py",
    }


@app.route("/api/upload", methods=["POST"])
def upload_file():
    if "model_file" not in request.files:
        abort(400, description="Missing model_file")

    uploaded = request.files["model_file"]
    if uploaded.filename != ALLOWED_FILE:
        abort(400, description="File must be named net.py")

    destination = path.join(UPLOAD_FOLDER, secure_filename(uploaded.filename))
    uploaded.save(destination)
    try:
        model_hash = validate_model_source(destination)
    except (SyntaxError, UnicodeDecodeError, ValueError) as error:
        abort(400, description=str(error))

    model = load_model()
    trained_model, metrics = train_model(model)
    torch.save(trained_model.state_dict(), path.join(BASE_DIR, SAVED_MODEL_NAME))
    metrics["model_sha256"] = model_hash

    return Response(
        response=json.dumps(metrics),
        status=200,
        mimetype="application/json",
    )


@app.route("/api/download")
def download_file():
    model_path = path.join(BASE_DIR, SAVED_MODEL_NAME)
    if not path.exists(model_path):
        abort(404, description="The global model has not been trained")
    return send_from_directory(BASE_DIR, SAVED_MODEL_NAME, as_attachment=True)


web3 = Web3(HTTPProvider(os.getenv("WEB3_PROVIDER", "http://127.0.0.1:7545")))
if not web3.isConnected():
    raise RuntimeError("Cannot connect to Ganache at the configured WEB3_PROVIDER")

accounts = web3.eth.accounts
workers, federated_train_loader, test_loader, worker_eth_accounts = (
    init_syft_workers(accounts)
)
contract = ContractClient(web3)
