import { useCallback, useEffect, useRef, useState } from 'react';
import { Phone, PhoneOff, Mic, Loader2 } from 'lucide-react';

const BrowserPhone = () => {
  const [status, setStatus] = useState('idle'); // idle, calling, connected, error
  const [isMuted, setIsMuted] = useState(false);
  const [agentSpeaking, setAgentSpeaking] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [callerName, setCallerName] = useState('');
  const [callerPhone, setCallerPhone] = useState('');
  
  const wsRef = useRef(null);
  const audioContextRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const scriptProcessorRef = useRef(null);
  const nextPlayTimeRef = useRef(0);
  const isMutedRef = useRef(false);
  const agentSpeakingRef = useRef(false);

  const setMutedState = (value) => {
    isMutedRef.current = value;
    setIsMuted(value);
  };

  const setSpeakingState = (value) => {
    agentSpeakingRef.current = value;
    setAgentSpeaking(value);
  };

  const resampleTo16k = (input, inputRate) => {
    if (inputRate === 16000) return input;
    const outputLength = Math.max(1, Math.round(input.length * 16000 / inputRate));
    const output = new Float32Array(outputLength);
    const step = inputRate / 16000;

    for (let i = 0; i < outputLength; i += 1) {
      const position = i * step;
      const left = Math.floor(position);
      const right = Math.min(left + 1, input.length - 1);
      const mix = position - left;
      output[i] = input[left] * (1 - mix) + input[right] * mix;
    }
    return output;
  };

  // Float32 to Int16 conversion
  const floatTo16BitPCM = (input) => {
    const output = new Int16Array(input.length);
    for (let i = 0; i < input.length; i++) {
      let s = Math.max(-1, Math.min(1, input[i]));
      output[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return output.buffer;
  };

  const endCall = useCallback((nextStatus = 'idle') => {
    const ws = wsRef.current;
    wsRef.current = null;

    if (ws) {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ event: 'stop' }));
      }
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close(1000, 'Call ended');
      }
    }

    if (scriptProcessorRef.current) {
      scriptProcessorRef.current.disconnect();
      scriptProcessorRef.current = null;
    }

    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }

    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }

    agentSpeakingRef.current = false;
    isMutedRef.current = false;
    setAgentSpeaking(false);
    setIsMuted(false);
    setStatus(nextStatus);
  }, []);

  const startCall = async () => {
    try {
      setStatus('calling');
      setErrorMessage('');

      // Create and resume audio synchronously from the click gesture. Waiting
      // until after network calls can leave AudioContext suspended in Chrome.
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      audioContextRef.current = new AudioContext();
      await audioContextRef.current.resume();
      nextPlayTimeRef.current = audioContextRef.current.currentTime;

      const healthResponse = await fetch('/health');
      const health = await healthResponse.json();
      if (!healthResponse.ok || health.services?.sarvam !== 'configured' || health.services?.llm !== 'configured') {
        throw new Error('Add SARVAM_API_KEY and restart the backend before starting a call.');
      }

      // Get Microphone
      mediaStreamRef.current = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        }
      });

      const source = audioContextRef.current.createMediaStreamSource(mediaStreamRef.current);
      
      // Create a script processor to capture audio
      // (Deprecated but easiest for raw PCM capture without separate worker files)
      const bufferSize = 4096;
      scriptProcessorRef.current = audioContextRef.current.createScriptProcessor(bufferSize, 1, 1);
      
      scriptProcessorRef.current.onaudioprocess = (e) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        if (isMutedRef.current || agentSpeakingRef.current) return;

        const inputData = e.inputBuffer.getChannelData(0);
        const audio16k = resampleTo16k(inputData, audioContextRef.current.sampleRate);
        const pcmData = floatTo16BitPCM(audio16k);
        wsRef.current.send(pcmData);
      };

      // Connect graph: microphone -> scriptProcessor -> destination (muted to avoid feedback)
      source.connect(scriptProcessorRef.current);
      scriptProcessorRef.current.connect(audioContextRef.current.destination);

      // Connect only after the microphone pipeline and message handlers can be
      // installed, otherwise a fast server can send the greeting too early.
      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const params = new URLSearchParams();
      if (callerName) params.append('name', callerName);
      if (callerPhone) params.append('phone', callerPhone);
      const queryString = params.toString() ? `?${params.toString()}` : '';
      const ws = new WebSocket(`${wsProtocol}//${window.location.host}/voice/browser${queryString}`);
      wsRef.current = ws;
      ws.binaryType = 'arraybuffer';

      // WebSocket Handlers
      ws.onopen = () => {
        setStatus('connected');
      };

      ws.onmessage = (event) => {
        if (typeof event.data === 'string') {
          // JSON control messages
          try {
            const data = JSON.parse(event.data);
            if (data.event === 'playback_start') setSpeakingState(true);
            if (data.event === 'playback_complete') setSpeakingState(false);
            if (data.event === 'error') {
              setErrorMessage(data.message || 'The voice service returned an error.');
              endCall('error');
            }
          } catch {
            setErrorMessage('The voice service returned an invalid response.');
          }
        } else {
          // Binary audio data (16kHz Int16 PCM) from AI
          playAudioChunk(event.data);
        }
      };

      ws.onclose = (event) => {
        if (wsRef.current !== ws) return;
        if (event.code !== 1000) {
          setErrorMessage((current) => current || 'The voice connection closed unexpectedly.');
          endCall('error');
        } else {
          endCall();
        }
      };

      ws.onerror = () => {
        setErrorMessage('Unable to connect to the voice service.');
      };

    } catch (err) {
      console.error("Failed to start call", err);
      setErrorMessage(err instanceof Error ? err.message : 'Unable to start the simulator.');
      endCall('error');
    }
  };

  const playAudioChunk = (arrayBuffer) => {
    if (!audioContextRef.current) return;
    
    // Convert Int16 PCM to Float32
    const int16Array = new Int16Array(arrayBuffer);
    const float32Array = new Float32Array(int16Array.length);
    for (let i = 0; i < int16Array.length; i++) {
      float32Array[i] = int16Array[i] / 0x8000;
    }

    const audioBuffer = audioContextRef.current.createBuffer(1, float32Array.length, 16000);
    audioBuffer.getChannelData(0).set(float32Array);

    const source = audioContextRef.current.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(audioContextRef.current.destination);

    // Schedule playback to avoid clipping/stuttering
    const currentTime = audioContextRef.current.currentTime;
    if (nextPlayTimeRef.current < currentTime) {
      nextPlayTimeRef.current = currentTime + 0.05; // Small buffer
    }
    
    source.start(nextPlayTimeRef.current);
    nextPlayTimeRef.current += audioBuffer.duration;
  };

  const toggleMute = () => {
    const nextMuted = !isMutedRef.current;
    setMutedState(nextMuted);
    // Send barge-in clear event if we unmute while agent is speaking
    if (!nextMuted && agentSpeakingRef.current && wsRef.current?.readyState === WebSocket.OPEN) {
       wsRef.current.send(JSON.stringify({ event: 'clear' }));
       setSpeakingState(false);
       // Reset playback scheduler
       if(audioContextRef.current) {
          nextPlayTimeRef.current = audioContextRef.current.currentTime;
       }
    }
  };

  useEffect(() => {
    return () => {
      endCall(); // Cleanup on unmount
    };
  }, [endCall]);

  return (
    <div className="bg-white rounded-lg p-8 border border-gray-200 shadow-sm max-w-sm w-full flex flex-col items-center">
      <h3 className="text-lg font-semibold text-gray-900 mb-1">Call Simulator</h3>
      <p className="text-xs text-gray-500 mb-8 text-center">
        Test the AI agent locally using your microphone.
      </p>

      {errorMessage && (
        <div className="mb-5 w-full rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700" role="alert">
          {errorMessage}
        </div>
      )}

      {status === 'idle' && (
        <div className="w-full mb-6 space-y-3">
          <input
            type="text"
            placeholder="Your Name (optional)"
            className="w-full text-sm border border-gray-300 rounded-md px-3 py-2 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            value={callerName}
            onChange={(e) => setCallerName(e.target.value)}
          />
          <input
            type="tel"
            placeholder="Phone Number (optional)"
            className="w-full text-sm border border-gray-300 rounded-md px-3 py-2 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            value={callerPhone}
            onChange={(e) => setCallerPhone(e.target.value)}
          />
        </div>
      )}

      {/* Status Avatar */}
      <div className={`w-24 h-24 rounded-full flex items-center justify-center mb-8 transition-all duration-300 ${
        status === 'connected' 
          ? agentSpeaking 
            ? 'bg-blue-50 border-2 border-blue-200' 
            : 'bg-green-50 border-2 border-green-200'
          : status === 'calling' 
            ? 'bg-amber-50 border-2 border-amber-200'
            : 'bg-gray-50 border-2 border-gray-200'
      }`}>
        {status === 'calling' ? (
          <Loader2 className="w-8 h-8 text-amber-500 animate-spin" />
        ) : status === 'connected' ? (
          <div className="flex flex-col items-center">
            <Phone className={`w-8 h-8 mb-1 ${agentSpeaking ? 'text-blue-600' : 'text-green-600'}`} />
            <span className="text-[10px] font-medium text-gray-600 uppercase tracking-wider">
              {agentSpeaking ? 'Speaking' : 'Listening'}
            </span>
          </div>
        ) : (
          <Phone className="w-8 h-8 text-gray-400" />
        )}
      </div>

      {/* Controls */}
      <div className="flex gap-3 w-full">
        {status === 'connected' && (
          <button
            onClick={toggleMute}
            className={`p-3 rounded-md flex-1 flex justify-center items-center transition-colors border ${
              isMuted 
                ? 'bg-red-50 text-red-600 border-red-200 hover:bg-red-100' 
                : 'bg-white text-gray-600 hover:bg-gray-50 border-gray-200'
            }`}
          >
            <Mic className="w-5 h-5" />
          </button>
        )}

        {status === 'idle' || status === 'error' ? (
          <button
            onClick={startCall}
            className="flex-1 bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 rounded-md py-3 flex justify-center items-center gap-2 text-sm font-medium transition-colors"
          >
            <Phone className="w-4 h-4" />
            Start Call
          </button>
        ) : (
          <button
            onClick={() => endCall()}
            className="flex-1 bg-white border border-red-200 hover:bg-red-50 text-red-600 rounded-md py-3 flex justify-center items-center gap-2 text-sm font-medium transition-colors"
          >
            <PhoneOff className="w-4 h-4" />
            End Call
          </button>
        )}
      </div>
    </div>
  );
};

export default BrowserPhone;
