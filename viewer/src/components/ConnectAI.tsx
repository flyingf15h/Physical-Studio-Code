// "Design your own" on screen 1: the visitor's own AI designs through our MCP server.
// 1 get a personal key (POST /api/connect), 2 add the server to Claude Code / Claude Desktop /
// Cursor, 3 copy the prompt into it. The AI exports, and the guide shows up under Your projects.
import { useState } from 'react'
import { connectKey } from '../api'
import { savedKey, saveKey } from '../projects'
import './ConnectAI.css'

const MCP_URL = `${location.origin}/mcp`

/** Said after the visitor's own words, so their AI uses the tools the way the design guide asks. */
export const PROMPT_SUFFIX =
  "\n\nDesign this with the physical-studio tools: use real parts from the library, look up each part's real look online and set it with set_part_look, check the fit, write one step per part, then export and give me the guide link."

const CLIENTS = [
  {
    id: 'claude-code',
    label: 'Claude Code',
    hint: 'Run this in your terminal, then restart Claude Code.',
    text: (key: string) => `claude mcp add --transport http physical-studio ${MCP_URL} --header "Authorization: Bearer ${key}"`,
  },
  {
    id: 'claude-desktop',
    label: 'Claude Desktop',
    hint: 'Settings → Developer → Edit Config, add this to claude_desktop_config.json, then restart Claude Desktop. Needs Node.js.',
    text: (key: string) =>
      JSON.stringify(
        { mcpServers: { 'physical-studio': { command: 'npx', args: ['-y', 'mcp-remote', MCP_URL, '--header', `Authorization:Bearer ${key}`] } } },
        null,
        2,
      ),
  },
  {
    id: 'cursor',
    label: 'Cursor and others',
    hint: 'Add to ~/.cursor/mcp.json (or your client\'s MCP settings): a streamable HTTP server with a bearer header.',
    text: (key: string) =>
      JSON.stringify({ mcpServers: { 'physical-studio': { url: MCP_URL, headers: { Authorization: `Bearer ${key}` } } } }, null, 2),
  },
]

function Copy({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [done, setDone] = useState(false)
  return (
    <button
      type="button"
      className="connect-copy"
      onClick={() => {
        void navigator.clipboard?.writeText(text).then(() => {
          setDone(true)
          setTimeout(() => setDone(false), 1500)
        })
      }}
    >
      {done ? 'Copied' : label}
    </button>
  )
}

interface Props {
  prompt: string
  setPrompt: (text: string) => void
  onKey: () => void // a new key was saved
}

export function ConnectAI({ prompt, setPrompt, onKey }: Props) {
  const [key, setKey] = useState(savedKey)
  const [client, setClient] = useState(CLIENTS[0].id)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const chosen = CLIENTS.find((c) => c.id === client)!

  const getKey = async () => {
    setBusy(true)
    setError(null)
    try {
      const { key } = await connectKey()
      saveKey(key)
      setKey(key)
      onKey()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <ol className="connect">
      <li>
        <h3>Get your key</h3>
        {key ? (
          <div className="connect-row">
            <code className="connect-key" title="Your personal key: keep it to yourself">
              {key.slice(0, 7)}…{key.slice(-4)}
            </code>
            <Copy text={key} label="Copy key" />
            <button type="button" className="connect-link" onClick={getKey} disabled={busy}>
              New key
            </button>
          </div>
        ) : (
          <button type="button" className="describe-go" onClick={getKey} disabled={busy}>
            {busy ? 'Getting a key…' : 'Get my key'}
          </button>
        )}
        <p className="connect-note">Your own workspace on our design server. It's saved in this browser.</p>
        {error && <p className="describe-error">{error}</p>}
      </li>
      <li className={key ? '' : 'connect-off'}>
        <h3>Connect your AI</h3>
        <div className="connect-tabs" role="tablist">
          {CLIENTS.map((c) => (
            <button
              key={c.id}
              type="button"
              role="tab"
              aria-selected={c.id === client}
              className={c.id === client ? 'active' : ''}
              onClick={() => setClient(c.id)}
            >
              {c.label}
            </button>
          ))}
        </div>
        <p className="connect-note">{chosen.hint}</p>
        <div className="connect-code">
          <pre>{chosen.text(key ?? 'YOUR_KEY')}</pre>
          {key && <Copy text={chosen.text(key)} />}
        </div>
      </li>
      <li className={key ? '' : 'connect-off'}>
        <h3>Ask it to build your project</h3>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="e.g. Traffic light for an Arduino Uno: red, yellow and green LEDs in a column on the lid, a crosswalk button, USB accessible on the side."
          aria-label="Your project"
          rows={3}
        />
        <div className="connect-row">
          <Copy text={prompt.trim() + PROMPT_SUFFIX} label="Copy prompt for your AI" />
          <span className="connect-note">Paste it into your AI. When it finishes it gives you the guide link, and the guide shows up under Your projects.</span>
        </div>
      </li>
    </ol>
  )
}
