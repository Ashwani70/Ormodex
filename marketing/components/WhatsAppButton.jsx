import Link from "next/link";

// Floating WhatsApp CTA. Set NEXT_PUBLIC_WHATSAPP (digits, country code, no +)
// in the environment; defaults to a placeholder so the button always renders.
const PHONE = process.env.NEXT_PUBLIC_WHATSAPP || "919056908758";
const MSG = encodeURIComponent("Hi! I'd like to know more about Ormodex ERP.");

export default function WhatsAppButton() {
  return (
    <Link
      href={`https://wa.me/${PHONE}?text=${MSG}`}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="Chat on WhatsApp"
      className="fixed bottom-5 right-5 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-[#25D366] shadow-lg transition-transform hover:scale-110"
    >
      <svg width="28" height="28" viewBox="0 0 32 32" fill="white" aria-hidden="true">
        <path d="M16.001 3C9.373 3 4 8.373 4 15c0 2.122.555 4.114 1.527 5.84L4 29l8.34-1.5A11.93 11.93 0 0016 27c6.627 0 12-5.373 12-12S22.628 3 16.001 3zm0 21.6c-1.74 0-3.36-.46-4.77-1.26l-.34-.2-4.95.89.9-4.83-.22-.36A9.55 9.55 0 016.4 15c0-5.293 4.307-9.6 9.6-9.6s9.6 4.307 9.6 9.6-4.306 9.6-9.6 9.6zm5.27-7.18c-.29-.145-1.71-.844-1.975-.94-.265-.097-.458-.145-.65.145-.193.29-.747.94-.916 1.13-.169.193-.337.217-.626.072-.29-.145-1.223-.45-2.33-1.437-.86-.767-1.44-1.715-1.61-2.005-.169-.29-.018-.446.127-.59.13-.13.29-.337.434-.506.145-.169.193-.29.29-.483.097-.193.048-.362-.024-.507-.072-.145-.65-1.566-.89-2.146-.235-.563-.473-.486-.65-.495l-.554-.01c-.193 0-.506.072-.771.362-.265.29-1.012.989-1.012 2.41 0 1.422 1.036 2.795 1.18 2.988.145.193 2.04 3.115 4.943 4.368.69.298 1.228.476 1.648.61.692.22 1.322.189 1.82.115.555-.083 1.71-.699 1.95-1.374.24-.676.24-1.255.169-1.374-.072-.12-.265-.193-.554-.337z" />
      </svg>
    </Link>
  );
}
