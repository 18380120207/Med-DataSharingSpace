import React, { Component } from 'react';
import axios from 'axios';
import { store } from 'react-notifications-component';
import 'react-notifications-component/dist/theme.css';
import 'animate.css';

import Web3 from 'web3';
import Contributions from '../Contributions.json';

const API_BASE = 'http://localhost:5000';
const TRAINING_STAKE_ETH = '1';

const UploadIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" />
    <path d="M5 13v6h14v-6" />
  </svg>
);

const FileIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="M7 3h7l4 4v14H7V3Z" />
    <path d="M14 3v5h5M10 13h5M10 17h4" />
  </svg>
);

const ArrowIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="M5 12h14M14 7l5 5-5 5" />
  </svg>
);

const DownloadIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="M12 4v11m0 0 4-4m-4 4-4-4M5 20h14" />
  </svg>
);

class UploadScreen extends Component {
  constructor(props) {
    super(props);
    this.fileInput = React.createRef();
    this.state = {
      selectedFile: null,
      training: false,
      training_completed: false,
      web3: null,
      federatedContract: null,
      account: null,
      isDragging: false,
      result: null,
      backendStatus: null
    };
  }

  async componentDidMount() {
    this.loadBackendStatus();
    await this.loadWeb3();
    if (window.web3) await this.loadBlockchainData();
  }

  loadBackendStatus = async () => {
    try {
      const response = await axios.get(`${API_BASE}/api/status`);
      this.setState({ backendStatus: response.data });
    } catch (error) {
      this.setState({ backendStatus: null });
    }
  };

  loadWeb3 = async () => {
    try {
      if (window.ethereum) {
        window.web3 = new Web3(window.ethereum);
        await window.ethereum.enable();
      } else if (window.web3) {
        window.web3 = new Web3(window.web3.currentProvider);
      } else {
        this.notify('未检测到钱包', '请安装并启用 MetaMask 后再提交模型。', 'warning');
        return;
      }
      this.setState({ web3: window.web3 });
    } catch (error) {
      this.notify('钱包连接未完成', '请在 MetaMask 中授权连接后重试。', 'warning');
    }
  };

  loadBlockchainData = async () => {
    try {
      const web3 = window.web3;
      const accounts = await web3.eth.getAccounts();
      const networkId = await web3.eth.net.getId();
      const networkData = Contributions.networks[networkId];

      if (networkData) {
        this.setState({
          account: accounts[0],
          federatedContract: new web3.eth.Contract(
            Contributions.abi,
            networkData.address
          )
        });
      } else {
        this.setState({ account: accounts[0] });
        this.notify('网络不匹配', '当前网络中未检测到已部署的贡献度合约。', 'warning');
      }
    } catch (error) {
      this.notify('链上数据读取失败', '请检查钱包网络与本地区块链服务。', 'danger');
    }
  };

  notify = (title, message, type = 'info', duration = 5000) => {
    store.addNotification({
      title,
      message,
      type,
      container: 'bottom-center',
      animationIn: ['animated', 'fadeInUp'],
      animationOut: ['animated', 'fadeOutDown'],
      dismiss: { duration }
    });
  };

  isValidFile = file => {
    if (!file || file.name !== 'net.py') return false;
    const validTypes = ['text/plain', 'text/x-python', 'application/octet-stream'];
    return !file.type || validTypes.indexOf(file.type) !== -1;
  };

  selectFile = file => {
    if (!file) return;
    if (!this.isValidFile(file)) {
      this.notify('模型文件不符合要求', '请选择名称为 net.py 的 Python 源文件。', 'danger');
      return;
    }
    if (file.size > 512 * 1024) {
      this.notify('模型文件过大', '模型结构描述文件不能超过 512 KB。', 'danger');
      return;
    }
    this.setState({
      selectedFile: file,
      training_completed: false,
      result: null
    });
  };

  onChangeHandler = event => {
    const file = event.target.files[0];
    this.selectFile(file);
    if (!this.isValidFile(file)) event.target.value = null;
  };

  onDragOver = event => {
    event.preventDefault();
    this.setState({ isDragging: true });
  };

  onDragLeave = event => {
    event.preventDefault();
    this.setState({ isDragging: false });
  };

  onDrop = event => {
    event.preventDefault();
    this.setState({ isDragging: false });
    this.selectFile(event.dataTransfer.files[0]);
  };

  openFilePicker = () => {
    if (!this.state.training && this.fileInput.current) {
      this.fileInput.current.click();
    }
  };

  onDropZoneKeyDown = event => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      this.openFilePicker();
    }
  };

  onDLClickHandler = () => {
    fetch(`${API_BASE}/api/download`)
      .then(response => {
        if (!response.ok) throw new Error('Download failed');
        return response.blob();
      })
      .then(blob => {
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'model.pt';
        link.click();
        window.URL.revokeObjectURL(url);
        this.setState({
          training_completed: false,
          training: false,
          selectedFile: null,
          result: null
        });
        if (this.fileInput.current) this.fileInput.current.value = null;
      })
      .catch(() => {
        this.notify('下载失败', '后端暂时无法提供全局模型，请稍后重试。', 'danger', 10000);
      });
  };

  onClickHandler = async () => {
    const { selectedFile, web3, federatedContract } = this.state;
    if (!selectedFile) {
      this.notify('请先选择模型', '上传 net.py 后即可发起安全聚合。', 'warning');
      return;
    }
    if (!web3 || !federatedContract) {
      this.notify('链上服务未就绪', '请连接 MetaMask，并切换到合约部署网络。', 'warning');
      return;
    }

    this.notify('安全任务已发起', '正在进行链上登记、隐私扰动与压缩聚合。', 'success', 7000);
    this.setState({ training: true, training_completed: false, result: null });

    const data = new FormData();
    data.append('model_file', selectedFile);

    try {
      const accounts = await web3.eth.getAccounts();
      const fileContent = await selectedFile.arrayBuffer();
      const hashResult = web3.utils.soliditySha3(
        web3.utils.bytesToHex(new Uint8Array(fileContent))
      );

      await federatedContract.methods.request_training(hashResult).send({
        from: accounts[0],
        value: web3.utils.toWei(TRAINING_STAKE_ETH, 'Ether')
      });

      const response = await axios.post(`${API_BASE}/api/upload`, data, {});
      this.setState({
        training_completed: true,
        result: response.data
      });
      this.notify(
        '聚合训练完成',
        `验证准确率：${this.formatPercent(response.data.accuracy)}`,
        'info',
        7000
      );
    } catch (error) {
      this.setState({ training: false });
      const message = error.response && error.response.data
        ? '模型校验或训练失败，请检查文件与后端日志。'
        : '链上交易或训练服务未完成，请检查 Ganache、MetaMask 与 Flask。';
      this.notify('安全聚合失败', message, 'danger', 10000);
    }
  };

  formatPercent = value => {
    const number = Number(value);
    if (Number.isNaN(number)) return '--';
    return `${(number * 100).toFixed(2)}%`;
  };

  renderAction = () => {
    const { training, training_completed, selectedFile } = this.state;
    if (training && !training_completed) {
      return (
        <div className="training-status">
          <span className="loader-ring" />
          <div>
            <strong>正在执行安全聚合</strong>
            <small>链上登记、隐私扰动、压缩与训练同步进行</small>
          </div>
        </div>
      );
    }
    if (training_completed) {
      return (
        <button type="button" className="primary-button download-button" onClick={this.onDLClickHandler}>
          <DownloadIcon />
          下载全局模型
        </button>
      );
    }
    return (
      <button
        type="button"
        className="primary-button"
        onClick={this.onClickHandler}
        disabled={!selectedFile}
      >
        发起安全聚合
        <ArrowIcon />
      </button>
    );
  };

  renderResult = () => {
    const { result } = this.state;
    if (!result) return null;

    const contributions = result.contributions || [];
    const compression = result.compression || {};
    return (
      <div className="result-area">
        <div className="result-panel">
          <div>
            <span>验证准确率</span>
            <strong>{this.formatPercent(result.accuracy)}</strong>
          </div>
          <div>
            <span>通信量降低</span>
            <strong>{compression.reduction_percent || 0}%</strong>
          </div>
          <div>
            <span>参数稀疏度</span>
            <strong>{compression.sparsity_percent || 0}%</strong>
          </div>
          <div>
            <span>隐私流水线</span>
            <strong>已启用</strong>
          </div>
        </div>

        {contributions.length > 0 && (
          <div className="contribution-card">
            <div className="result-heading">
              <div>
                <span>CONTRIBUTION LEDGER</span>
                <strong>节点贡献度</strong>
              </div>
              <small>{contributions.length} 个协作节点</small>
            </div>
            <div className="contribution-list">
              {contributions.map((item, index) => (
                <div className="contribution-row" key={item.node || index}>
                  <span>{item.node || `节点 ${index + 1}`}</span>
                  <div className="contribution-track">
                    <i style={{ width: `${Math.max(2, item.percent || 0)}%` }} />
                  </div>
                  <strong>{Number(item.percent || 0).toFixed(2)}%</strong>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  render() {
    const {
      selectedFile,
      training,
      training_completed,
      account,
      isDragging,
      backendStatus
    } = this.state;
    const uploadClass = [
      'drop-zone',
      isDragging ? 'is-dragging' : '',
      selectedFile ? 'has-file' : '',
      training ? 'is-disabled' : ''
    ].filter(Boolean).join(' ');

    return (
      <section className="console-card">
        <div className="console-head">
          <div>
            <span className="section-kicker">MODEL WORKSPACE</span>
            <h2>模型聚合中心</h2>
          </div>
          <div className="service-states">
            <div className={`wallet-state ${backendStatus ? 'is-connected' : ''}`}>
              <span />
              {backendStatus ? '训练服务在线' : '训练服务离线'}
            </div>
            <div className={`wallet-state ${account ? 'is-connected' : ''}`}>
              <span />
              {account ? `${account.slice(0, 6)}...${account.slice(-4)}` : '钱包未连接'}
            </div>
          </div>
        </div>

        <div className="step-row">
          <div className="step is-active"><span>01</span>校验登记</div>
          <i />
          <div className={training ? 'step is-active' : 'step'}><span>02</span>安全聚合</div>
          <i />
          <div className={training_completed ? 'step is-active' : 'step'}><span>03</span>获取结果</div>
        </div>

        <input
          ref={this.fileInput}
          className="file-input"
          type="file"
          accept=".py,text/plain,text/x-python"
          onChange={this.onChangeHandler}
          tabIndex="-1"
        />
        <div
          role="button"
          tabIndex={training ? -1 : 0}
          aria-disabled={training}
          className={uploadClass}
          onClick={this.openFilePicker}
          onKeyDown={this.onDropZoneKeyDown}
          onDragOver={this.onDragOver}
          onDragLeave={this.onDragLeave}
          onDrop={this.onDrop}
        >
          {selectedFile ? (
            <>
              <span className="upload-icon file-ready"><FileIcon /></span>
              <strong>{selectedFile.name}</strong>
              <p>{(selectedFile.size / 1024).toFixed(1)} KB · 等待安全校验</p>
              {!training && <small>点击可重新选择</small>}
            </>
          ) : (
            <>
              <span className="upload-icon"><UploadIcon /></span>
              <strong>拖放模型结构文件到这里</strong>
              <p>系统将校验语法、生成指纹并完成链上登记</p>
              <small>仅支持名称为 <code>net.py</code>、不超过 512 KB 的文件</small>
            </>
          )}
        </div>

        {this.renderResult()}

        <div className="console-footer">
          <p>
            <span className="mini-shield">✓</span>
            上传源码不会被直接执行；训练使用服务端已审计模型，文件哈希用于可信登记
          </p>
          {this.renderAction()}
        </div>
      </section>
    );
  }
}

export default UploadScreen;
