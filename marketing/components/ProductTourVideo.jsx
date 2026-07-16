"use client";

import React, { useState, useEffect, useRef } from "react";

const STEPS = [
  {
    id: "analytics",
    label: "Smart Analytics",
    title: "Real-time business intelligence",
    desc: "Interactive graphs showing revenue, order trends, and employee activity updated instantly."
  },
  {
    id: "ledger",
    label: "Accrual Ledger",
    title: "Auto-posted double-entry journals",
    desc: "Transactions automatically post balanced entries to Accounts Payable, Inventory asset, and GST ledgers."
  },
  {
    id: "inventory",
    label: "FIFO Inventory",
    title: "Multi-warehouse stock ledger tracking",
    desc: "Derives on-hand stock and valuations (FIFO/WA) per warehouse without spreadsheet drift."
  },
  {
    id: "einvoice",
    label: "e-Invoicing & GST",
    title: "Direct Government Portal integration",
    desc: "Generate IRN numbers, dynamic QR codes, and e-Way Bills in one click right from the billing screen."
  }
];

export default function ProductTourVideo() {
  const [isPlaying, setIsPlaying] = useState(true);
  const [currentStep, setCurrentStep] = useState(0);
  const [progress, setProgress] = useState(0);
  const timerRef = useRef(null);

  // Auto-advance logic
  useEffect(() => {
    if (!isPlaying) {
      if (timerRef.current) clearInterval(timerRef.current);
      return;
    }

    const intervalTime = 50; // ms
    const stepDuration = 5000; // 5 seconds per step
    const increment = (intervalTime / stepDuration) * 100;

    timerRef.current = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 100) {
          setCurrentStep((prevStep) => {
            if (prevStep >= STEPS.length - 1) {
              return 0; // Loop back to the first step and keep playing
            }
            return prevStep + 1;
          });
          return 0;
        }
        return prev + increment;
      });
    }, intervalTime);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isPlaying, currentStep]);

  const handlePlayToggle = () => {
    setIsPlaying(!isPlaying);
  };

  const handleStepClick = (index) => {
    setCurrentStep(index);
    setProgress(0);
    setIsPlaying(true);
  };

  return (
    <div className="relative mx-auto w-full max-w-4xl overflow-hidden rounded-3xl border border-slate-200 bg-[#0B0F19] text-white shadow-card transition-all duration-300">
      
      {/* ── 1. Video Player Top Bar (Header/Tabs) ── */}
      <div className="flex flex-wrap items-center justify-between border-b border-slate-800 bg-[#0D1424] px-6 py-4">
        <div className="flex items-center gap-2">
          <span className="flex h-3 w-3 items-center justify-center rounded-full bg-red-500" />
          <span className="flex h-3 w-3 items-center justify-center rounded-full bg-yellow-500" />
          <span className="flex h-3 w-3 items-center justify-center rounded-full bg-green-500" />
          <span className="ml-3 font-mono text-xs uppercase tracking-wider text-slate-400">Ormodex ERP - Product Demo</span>
        </div>
        
        {/* Play/Pause Control */}
        <button 
          onClick={handlePlayToggle}
          className="rounded-full bg-primary/10 px-4 py-1.5 text-xs font-semibold text-primary transition hover:bg-primary/20"
        >
          {isPlaying ? "⏸ Pause Tour" : "▶ Play Tour"}
        </button>
      </div>

      {/* ── 2. Tour Step Navigation Tabs ── */}
      <div className="grid grid-cols-4 border-b border-slate-800 bg-[#0E172B] text-center text-xs font-medium">
        {STEPS.map((step, idx) => {
          const isActive = currentStep === idx;
          return (
            <button
              key={step.id}
              onClick={() => handleStepClick(idx)}
              className={`relative py-3 transition-colors hover:text-white ${isActive ? "text-primary font-bold" : "text-slate-400"}`}
            >
              {step.label}
              {/* Animated Progress Bar under the tab */}
              {isActive && (
                <div 
                  className="absolute bottom-0 left-0 h-0.5 bg-primary transition-all duration-75"
                  style={{ width: `${progress}%` }}
                />
              )}
            </button>
          );
        })}
      </div>

      {/* ── 3. Screen content / Cinematic Simulation viewport ── */}
      <div className="relative aspect-video w-full flex items-center justify-center p-6 sm:p-10">
        
        {/* Cover Overlay (When not playing and at start) */}
        {!isPlaying && progress === 0 && currentStep === 0 && (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-[#090D1A]/95 p-6 text-center">
            {/* Backdrop dashboard grid pattern */}
            <div className="absolute inset-0 opacity-10 bg-[linear-gradient(to_right,#808080_1px,transparent_1px),linear-gradient(to_bottom,#808080_1px,transparent_1px)] bg-[size:24px_24px]" />
            
            <div className="relative mb-5 flex h-24 w-24 items-center justify-center rounded-full bg-primary/10 text-primary shadow-glow transition hover:scale-105">
              <button
                onClick={() => setIsPlaying(true)}
                className="flex h-20 w-20 items-center justify-center rounded-full bg-primary text-white shadow-lg transition hover:scale-110"
                aria-label="Play product tour"
              >
                <span className="ml-1 text-3xl">▶</span>
              </button>
            </div>
            
            <h3 className="text-2xl font-bold tracking-tight text-white">Experience Ormodex ERP</h3>
            <p className="mt-2 max-w-md text-sm text-slate-400">
              Click play to take an animated 20-second walkthrough of our database flow, automatic bookkeeping, and government integrations.
            </p>
          </div>
        )}

        {/* Cinematic Content Renderer based on current Step */}
        <div className="w-full h-full flex flex-col justify-between">
          
          {/* Header Description of the active step */}
          <div className="mb-4 animate-fade-up">
            <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-primary">{STEPS[currentStep].label} Demo</span>
            <h4 className="text-lg sm:text-xl font-bold text-white mt-0.5">{STEPS[currentStep].title}</h4>
            <p className="text-xs text-slate-400 mt-1 max-w-2xl">{STEPS[currentStep].desc}</p>
          </div>

          {/* Core Visual Simulation Area (Simulated browser views) */}
          <div className="flex-1 rounded-2xl border border-slate-800 bg-[#0E1626]/90 p-4 shadow-inner relative overflow-hidden flex flex-col justify-center">
            
            {/* ── STEP 1: SMART ANALYTICS ── */}
            {currentStep === 0 && (
              <div className="space-y-4 animate-fade-up w-full">
                {/* Stats row */}
                <div className="grid grid-cols-3 gap-3">
                  {[
                    { label: "Total Revenue", val: "₹18,45,290", diff: "+14.2%" },
                    { label: "Active Orders", val: "512", diff: "+8.7%" },
                    { label: "Low Stock Alert", val: "2 Items", diff: "Critical" }
                  ].map((stat, i) => (
                    <div key={i} className="bg-[#121E36] p-2.5 rounded-lg border border-slate-800/80">
                      <div className="text-[10px] text-slate-400">{stat.label}</div>
                      <div className="text-sm font-bold text-white mt-0.5">{stat.val}</div>
                      <div className={`text-[9px] font-mono font-bold mt-0.5 ${i === 2 ? 'text-red-400' : 'text-green-400'}`}>{stat.diff}</div>
                    </div>
                  ))}
                </div>

                {/* Animated Line Chart SVG */}
                <div className="h-28 w-full bg-[#121E36]/50 rounded-lg p-2 flex flex-col justify-between border border-slate-800/50">
                  <div className="flex justify-between items-center text-[9px] text-slate-400 font-mono">
                    <span>Revenue Trend (This Week)</span>
                    <span className="text-primary font-bold">LIVE METRIC UPDATES</span>
                  </div>
                  <div className="flex-1 flex items-end relative px-2">
                    <svg className="w-full h-full" viewBox="0 0 100 30" preserveAspectRatio="none">
                      <path 
                        d="M 0 30 Q 15 15, 30 22 T 60 5 T 90 2 T 100 2" 
                        fill="none" 
                        stroke="#4CAF4F" 
                        strokeWidth="1.5" 
                        strokeDasharray="100" 
                        strokeDashoffset={100 - (progress * 1)}
                        className="transition-all duration-300"
                      />
                      {/* Gradient fill */}
                      <path 
                        d="M 0 30 Q 15 15, 30 22 T 60 5 T 90 2 T 100 2 L 100 30 L 0 30 Z" 
                        fill="url(#analyticsChartGrad)" 
                        opacity="0.15" 
                      />
                      <defs>
                        <linearGradient id="analyticsChartGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#4CAF4F" />
                          <stop offset="100%" stopColor="#4CAF4F" stopOpacity="0" />
                        </linearGradient>
                      </defs>
                    </svg>
                  </div>
                </div>
              </div>
            )}

            {/* ── STEP 2: ACCRUAL LEDGER POSTING ── */}
            {currentStep === 1 && (
              <div className="space-y-3 animate-fade-up w-full">
                {/* Trigger Invoice entry simulation */}
                <div className="flex items-center justify-between bg-[#121E36] p-2.5 rounded-lg border border-slate-800">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-green-500 animate-ping" />
                    <span className="text-xs text-white font-mono">Transaction: Purchase Bill #PB-2026-004</span>
                  </div>
                  <span className="text-[10px] bg-primary/20 text-primary border border-primary/30 px-2 py-0.5 rounded-md font-mono">AUTO-POSTING</span>
                </div>

                {/* Double Entry Ledger representation */}
                <div className="bg-[#121E36]/60 border border-slate-800 rounded-lg overflow-hidden font-mono text-[10px]">
                  <div className="grid grid-cols-4 bg-[#0E172B] px-3 py-1.5 text-slate-400 font-bold border-b border-slate-800">
                    <span>Account Code</span>
                    <span>Account Name</span>
                    <span className="text-right">Debit (Dr)</span>
                    <span className="text-right">Credit (Cr)</span>
                  </div>
                  <div className="p-3 space-y-2">
                    <div className="grid grid-cols-4 text-green-400 transition-opacity duration-300">
                      <span>1200</span>
                      <span>Inventory Asset</span>
                      <span className="text-right">₹1,50,000.00</span>
                      <span className="text-right">—</span>
                    </div>
                    <div className="grid grid-cols-4 text-green-400 transition-opacity duration-300" style={{ transitionDelay: '300ms' }}>
                      <span>1500</span>
                      <span>GST Input Tax Credit</span>
                      <span className="text-right">₹27,000.00</span>
                      <span className="text-right">—</span>
                    </div>
                    <div className="grid grid-cols-4 text-yellow-400 transition-opacity duration-300" style={{ transitionDelay: '600ms' }}>
                      <span>2001</span>
                      <span className="pl-2">Accounts Payable</span>
                      <span className="text-right">—</span>
                      <span className="text-right">₹1,77,000.00</span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* ── STEP 3: FIFO INVENTORY VALUATION ── */}
            {currentStep === 2 && (
              <div className="space-y-3 animate-fade-up w-full">
                {/* Warehouse status */}
                <div className="grid grid-cols-2 gap-4">
                  
                  {/* Pune Warehouse */}
                  <div className="bg-[#121E36] p-3 rounded-lg border border-slate-800">
                    <div className="flex justify-between items-center text-xs">
                      <span className="font-bold text-white">Pune Main Warehouse</span>
                      <span className="text-[10px] text-slate-400 font-mono">FIFO Valuation</span>
                    </div>
                    <div className="mt-2 text-lg font-bold text-primary">₹3,42,000</div>
                    <div className="mt-1.5 h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                      <div 
                        className="h-full bg-primary transition-all duration-1000" 
                        style={{ width: isPlaying ? '72%' : '40%' }} 
                      />
                    </div>
                    <div className="mt-1 flex justify-between text-[9px] text-slate-400 font-mono">
                      <span>Stock Qty: 285 pcs</span>
                      <span>Capacity: 72%</span>
                    </div>
                  </div>

                  {/* Mumbai Warehouse */}
                  <div className="bg-[#121E36] p-3 rounded-lg border border-slate-800">
                    <div className="flex justify-between items-center text-xs">
                      <span className="font-bold text-white">Mumbai Export Yard</span>
                      <span className="text-[10px] text-slate-400 font-mono">FIFO Valuation</span>
                    </div>
                    <div className="mt-2 text-lg font-bold text-yellow-400">₹94,800</div>
                    <div className="mt-1.5 h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                      <div 
                        className="h-full bg-yellow-400 transition-all duration-1000" 
                        style={{ width: isPlaying ? '25%' : '10%' }} 
                      />
                    </div>
                    <div className="mt-1 flex justify-between text-[9px] text-slate-400 font-mono">
                      <span>Stock Qty: 79 pcs</span>
                      <span>Capacity: 25%</span>
                    </div>
                  </div>

                </div>

                {/* Stock Transfer animation */}
                <div className="bg-[#121E36]/40 p-2 rounded-lg border border-slate-800/60 text-[10px] font-mono flex items-center justify-between">
                  <span>TRANSFER OUT: 100 pcs from Pune</span>
                  <span className="text-slate-500">═══════ ✈ ═══════</span>
                  <span>TRANSFER IN: Mumbai (Cost layer preserved)</span>
                </div>
              </div>
            )}

            {/* ── STEP 4: ONE-CLICK E-INVOICING ── */}
            {currentStep === 3 && (
              <div className="grid grid-cols-5 gap-4 items-center animate-fade-up w-full">
                
                {/* Left side: Invoice Details */}
                <div className="col-span-3 bg-[#121E36] p-3 rounded-lg border border-slate-800 text-[10px] font-mono space-y-2">
                  <div className="font-bold text-white border-b border-slate-800 pb-1 flex justify-between">
                    <span>GST TAX INVOICE</span>
                    <span className="text-green-400 font-bold">READY</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Consignee:</span>
                    <span className="text-white">Rajesh Builders</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">GSTIN:</span>
                    <span className="text-white">27ABCDE1234F1Z5</span>
                  </div>
                  <div className="flex justify-between border-t border-slate-800 pt-1 text-slate-200">
                    <span>Taxable Amt:</span>
                    <span>₹1,50,000.00</span>
                  </div>
                  <div className="flex justify-between text-slate-200">
                    <span>GST (18%):</span>
                    <span>₹27,000.00</span>
                  </div>
                  <div className="flex justify-between text-primary font-bold border-t border-slate-800/80 pt-1">
                    <span>Grand Total:</span>
                    <span>₹1,77,000.00</span>
                  </div>
                </div>

                {/* Right side: e-Invoice API result */}
                <div className="col-span-2 flex flex-col items-center justify-center text-center space-y-2 bg-[#121E36]/40 p-3 rounded-lg border border-slate-800/60 min-h-[120px]">
                  
                  {progress < 40 ? (
                    <>
                      <div className="w-8 h-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                      <div className="text-[10px] font-mono text-slate-400">Calling NIC Portal...</div>
                    </>
                  ) : (
                    <>
                      {/* Dynamic QR Code representation */}
                      <svg className="w-16 h-16 bg-white p-1 rounded-md" viewBox="0 0 25 25" shapeRendering="crispEdges">
                        <path d="M0 0h7v7H0zm1 1v5h5V1zm1 1v3h3V2zm6-2h1v1H8zm1 1h1v2H9zm1-1h1v1h-1zm1 1h2v1h-2zm-3 2h1v1H8zm1 0h1v2H9zm1 1h1v1h-1zm5-4h7v7h-7zm1 1v5h5V1zm1 1v3h3V2zm-9 6h1v1H8zm1 1h2v1H9zm2-1h1v1h-1zm2 1h1v2h-1zm1-1h2v1h-2zm1 2h1v1h-1zm-7 4h1v1H8zm1-1h2v1H9zm1 2h1v1h-1zm-9 1h7v7H0zm1 1v5h5V1zm1 1v3h3V2z" fill="#000" />
                        <rect x="18" y="18" width="6" height="6" fill="#4CAF4F" />
                      </svg>
                      <div className="text-[9px] font-mono text-green-400 font-bold mt-1">✓ IRN GENERATED</div>
                      <div className="text-[8px] font-mono text-slate-500 select-all overflow-hidden text-ellipsis w-28 whitespace-nowrap">
                        56b73a218f...
                      </div>
                    </>
                  )}
                </div>

              </div>
            )}

          </div>

          {/* Bottom control feedback */}
          <div className="mt-4 flex items-center justify-between text-xs text-slate-500 font-mono">
            <span className="flex items-center gap-1.5">
              <span className={`h-2 w-2 rounded-full ${isPlaying ? 'bg-green-500 animate-pulse' : 'bg-yellow-500'}`} />
              {isPlaying ? "Simulating Live ERP Actions..." : "Walkthrough Paused."}
            </span>
            <span>Step {currentStep + 1} of 4</span>
          </div>

        </div>

      </div>

    </div>
  );
}
