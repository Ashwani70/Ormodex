/** @type {import('tailwindcss').Config} */
module.exports = {
    darkMode: ["class"],
    content: [
    "./src/**/*.{js,jsx,ts,tsx}",
    "./public/index.html"
  ],
  theme: {
  	extend: {
  		borderRadius: {
  			lg: 'var(--radius)',
  			md: 'calc(var(--radius) - 2px)',
  			sm: 'calc(var(--radius) - 4px)'
  		},
  		colors: {
  			background: 'hsl(var(--background))',
  			foreground: 'hsl(var(--foreground))',
  			surface: 'var(--surface)',
  			'border-strong': 'var(--border-strong)',
  			card: {
  				DEFAULT: 'hsl(var(--card))',
  				foreground: 'hsl(var(--card-foreground))'
  			},
  			popover: {
  				DEFAULT: 'hsl(var(--popover))',
  				foreground: 'hsl(var(--popover-foreground))'
  			},
  			primary: {
  				DEFAULT: 'hsl(var(--primary))',
  				foreground: 'hsl(var(--primary-foreground))'
  			},
  			secondary: {
  				DEFAULT: 'hsl(var(--secondary))',
  				foreground: 'hsl(var(--secondary-foreground))'
  			},
  			muted: {
  				DEFAULT: 'hsl(var(--muted))',
  				foreground: 'hsl(var(--muted-foreground))'
  			},
  			accent: {
  				DEFAULT: 'hsl(var(--accent))',
  				foreground: 'hsl(var(--accent-foreground))'
  			},
  			destructive: {
  				DEFAULT: 'hsl(var(--destructive))',
  				foreground: 'hsl(var(--destructive-foreground))'
  			},
  			border: 'hsl(var(--border))',
  			input: 'hsl(var(--input))',
  			ring: 'hsl(var(--ring))',
  			yellow: {
  				'50': 'rgb(var(--yellow-50) / <alpha-value>)',
  				'100': 'rgb(var(--yellow-100) / <alpha-value>)',
  				'200': 'rgb(var(--yellow-200) / <alpha-value>)',
  				'300': 'rgb(var(--yellow-300) / <alpha-value>)',
  				'400': 'rgb(var(--yellow-400) / <alpha-value>)',
  				'500': 'rgb(var(--yellow-500) / <alpha-value>)',
  				'600': 'rgb(var(--yellow-600) / <alpha-value>)',
  				'700': 'rgb(var(--yellow-700) / <alpha-value>)',
  				'800': 'rgb(var(--yellow-800) / <alpha-value>)',
  				'900': 'rgb(var(--yellow-900) / <alpha-value>)',
  				'950': 'rgb(var(--yellow-950) / <alpha-value>)',
  			},
  			zinc: {
  				'50': 'rgb(var(--zinc-50) / <alpha-value>)',
  				'100': 'rgb(var(--zinc-100) / <alpha-value>)',
  				'200': 'rgb(var(--zinc-200) / <alpha-value>)',
  				'300': 'rgb(var(--zinc-300) / <alpha-value>)',
  				'400': 'rgb(var(--zinc-400) / <alpha-value>)',
  				'500': 'rgb(var(--zinc-500) / <alpha-value>)',
  				'600': 'rgb(var(--zinc-600) / <alpha-value>)',
  				'700': 'rgb(var(--zinc-700) / <alpha-value>)',
  				'800': 'rgb(var(--zinc-800) / <alpha-value>)',
  				'900': 'rgb(var(--zinc-900) / <alpha-value>)',
  				'950': 'rgb(var(--zinc-950) / <alpha-value>)',
  			},
  			chart: {
  				'1': 'hsl(var(--chart-1))',
  				'2': 'hsl(var(--chart-2))',
  				'3': 'hsl(var(--chart-3))',
  				'4': 'hsl(var(--chart-4))',
  				'5': 'hsl(var(--chart-5))'
  			}
  		},
  		keyframes: {
  			'accordion-down': {
  				from: {
  					height: '0'
  				},
  				to: {
  					height: 'var(--radix-accordion-content-height)'
  				}
  			},
  			'accordion-up': {
  				from: {
  					height: 'var(--radix-accordion-content-height)'
  				},
  				to: {
  					height: '0'
  				}
  			}
  		},
  		animation: {
  			'accordion-down': 'accordion-down 0.2s ease-out',
  			'accordion-up': 'accordion-up 0.2s ease-out'
  		}
  	}
  },
  plugins: [require("tailwindcss-animate")],
};