import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

function collectFiles(dir: string, exts: string[]): string[] {
  const out: string[] = []
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      if (!['node_modules', '.venv', '__pycache__', 'dist'].includes(entry.name)) {
        out.push(...collectFiles(full, exts))
      }
    } else if (exts.some((e) => entry.name.endsWith(e))) {
      out.push(full)
    }
  }
  return out
}

describe('i18n and encoding integrity', () => {
  it('contains no corrupted accents (? between letters or replacement char)', () => {
    const root = path.resolve(__dirname, '../..')
    const files = [
      ...collectFiles(path.join(root, 'frontend/src'), ['.ts', '.tsx']),
      ...collectFiles(path.join(root, 'backend/app'), ['.py']),
    ]
    const bad: string[] = []
    const corruptedRe = /[A-Za-z?-?]\?[A-Za-z?-?]|\ufffd/
    for (const f of files) {
      if (f.endsWith('App.i18n.test.tsx')) continue
      const lines = fs.readFileSync(f, 'utf8').split(/\r?\n/)
      lines.forEach((line, idx) => {
        if (corruptedRe.test(line)) {
          bad.push(`${path.relative(root, f)}:${idx + 1}: ${line.trim()}`)
        }
      })
    }
    expect(bad).toEqual([])
  })
})
