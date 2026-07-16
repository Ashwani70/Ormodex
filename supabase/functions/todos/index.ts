import { withSupabase } from "@supabase/server"

export default {
  // Edge Function handler with withSupabase wrapper.
  // It handles JWT verification / auth mode validation automatically.
  fetch: withSupabase({ auth: "user" }, async (req, ctx) => {
    const url = new URL(req.url)
    const action = url.searchParams.get("action")

    try {
      // 1. Using RLS-scoped client (ctx.supabase)
      if (action === "rls-fetch") {
        const { data, error } = await ctx.supabase
          .from("todos")
          .select("*")
        
        if (error) throw error
        return Response.json({ success: true, data })
      }

      // 2. Using Admin client which bypasses RLS (ctx.supabaseAdmin)
      if (action === "admin-fetch") {
        const { data, error } = await ctx.supabaseAdmin
          .from("todos")
          .select("*")
        
        if (error) throw error
        return Response.json({ success: true, data })
      }

      // Default fallback
      const { data, error } = await ctx.supabase
        .from("todos")
        .select()
      
      if (error) throw error
      return Response.json({ success: true, data })

    } catch (err: any) {
      return Response.json({ success: false, error: err.message }, { status: 400 })
    }
  }),
}
