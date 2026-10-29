import React from 'react';
import './App.css';
import ReactNotifications from 'react-notifications-component';
import UploadScreen from './components/UploadScreen';

const ShieldIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="M12 3 5 6v5c0 4.6 2.9 8.6 7 10 4.1-1.4 7-5.4 7-10V6l-7-3Z" />
    <path d="m9 12 2 2 4-4" />
  </svg>
);

const NetworkIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <circle cx="12" cy="5" r="2.5" />
    <circle cx="5" cy="18" r="2.5" />
    <circle cx="19" cy="18" r="2.5" />
    <path d="m10.8 7.2-4.6 8.6M13.2 7.2l4.6 8.6M7.5 18h9" />
  </svg>
);

const ModelIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="M7 4h10l3 5-8 12L4 9l3-5Z" />
    <path d="m4 9 8 3 8-3M12 12v9M7 4l5 8 5-8" />
  </svg>
);

function App() {
  return (
    <div className="app-shell">
      <ReactNotifications />
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />

      <nav className="topbar">
        <div className="brand">
          <span className="brand-mark">
            <span />
            <span />
            <span />
          </span>
          <span className="brand-name">FedChain</span>
          <span className="brand-label">
            隐私计算平台
            <span className="brand-suffix">--智慧医疗协同建模方案</span>
          </span>
        </div>
        <div className="network-pill">
          <span className="status-dot" />
          联盟链网络
        </div>
      </nav>

      <main className="main-layout">
        <section className="hero-section">
          <div className="eyebrow">
            <span>BLOCKCHAIN</span>
            <i />
            <span>FEDERATED LEARNING</span>
          </div>
          <h1>
            让数据留在本地，
            <span>让智能安全流动</span>
          </h1>
          <p className="hero-copy">
            面向边缘算力网络的轻量化隐私安全共享空间。通过智能合约完成模型验证、
            贡献记录与可信聚合。
          </p>

          <div className="feature-grid">
            <article className="feature-card">
              <span className="feature-icon"><ShieldIcon /></span>
              <div>
                <strong>隐私保护</strong>
                <p>原始数据不离开本地节点</p>
              </div>
            </article>
            <article className="feature-card">
              <span className="feature-icon"><NetworkIcon /></span>
              <div>
                <strong>可信协作</strong>
                <p>链上记录全程可验证</p>
              </div>
            </article>
            <article className="feature-card">
              <span className="feature-icon"><ModelIcon /></span>
              <div>
                <strong>智能聚合</strong>
                <p>安全生成高质量全局模型</p>
              </div>
            </article>
          </div>
        </section>

        <UploadScreen />
      </main>

      <footer className="app-footer">
        <span>FEDCHAIN / SECURE COLLABORATIVE INTELLIGENCE</span>
        <span>区块链 · 联邦学习 · 边缘计算</span>
      </footer>
    </div>
  );
}

export default App;
