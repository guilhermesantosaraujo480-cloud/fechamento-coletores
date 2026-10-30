import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

// Redireciona o botão do e-mail para o WhatsApp e registra o clique.
// - grava em cliques_email.envio_id o parâmetro `envio` (id do e-mail enviado); sem ele, grava o protocolo (links antigos)
// - só redireciona para o WhatsApp (evita usar este endereço para levar o cliente a outros sites)
// - nunca deixa de redirecionar, mesmo que o registro do clique falhe
const PADRAO = 'https://wa.me/'
const PERMITIDOS = ['wa.me', 'api.whatsapp.com', 'web.whatsapp.com']

export function destinoSeguro(dest: string | null): string {
  if (!dest) return PADRAO
  const tentativas = [dest]
  try { tentativas.push(decodeURIComponent(dest)) } catch (_) { /* texto inválido: só a 1ª tentativa */ }
  for (const t of tentativas) {
    try {
      const u = new URL(t)
      if (u.protocol === 'https:' && PERMITIDOS.includes(u.hostname)) return u.toString()
    } catch (_) { /* tenta a próxima */ }
  }
  return PADRAO
}

export async function tratar(req: Request, gravar: (linha: Record<string, string>) => Promise<unknown>): Promise<Response> {
  const url = new URL(req.url)
  const protocolo = url.searchParams.get('protocolo') || ''
  const envio = url.searchParams.get('envio') || ''
  const identificador = envio || protocolo
  if (identificador) {
    try {
      await gravar({ envio_id: identificador.slice(0, 200), user_agent: req.headers.get('user-agent') || 'desconhecido' })
    } catch (_) { /* o cliente deve chegar ao WhatsApp mesmo assim */ }
  }
  return Response.redirect(destinoSeguro(url.searchParams.get('dest')), 302)
}

serve((req) => {
  const supabase = createClient(
    Deno.env.get('SUPABASE_URL') ?? '',
    Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''
  )
  return tratar(req, (linha) => supabase.from('cliques_email').insert(linha))
})
