import svelte from 'rollup-plugin-svelte';
import commonjs from '@rollup/plugin-commonjs';
import terser from '@rollup/plugin-terser';
import resolve from '@rollup/plugin-node-resolve';
import livereload from 'rollup-plugin-livereload';
import css from 'rollup-plugin-css-only';
import typescript from '@rollup/plugin-typescript'; // or from 'rollup-plugin-typescript2'
import autoPreprocess from 'svelte-preprocess';

const production = !process.env.ROLLUP_WATCH;

export default {
	input: 'src/svelte/main.ts',
	output: {
		sourcemap: true,
		format: 'iife',
		name: 'app',
		file: 'dist/bundle.js'
	},
	plugins: [
    typescript(),
		svelte({
      preprocess: autoPreprocess(),  // typescript
			compilerOptions: {
				// enable run-time checks when not in production
				dev: !production
			}
		}),
		// we'll extract any component CSS out into
		// a separate file - better for performance
		css({ output: 'bundle.css' }),

		// If you have external dependencies installed from
		// npm, you'll most likely need these plugins. In
		// some cases you'll need additional configuration -
		// consult the documentation for details:
		// https://github.com/rollup/plugins/tree/master/packages/commonjs
		resolve({
			browser: true,
      extensions: ['.mjs', '.js', '.json', '.node', '.svelte', '.ts', '.d.ts'],
			dedupe: ['svelte'],
			exportConditions: ['svelte']
		}),
		commonjs(),

		// Watch the `src/svelte` directory and refresh the
		// browser on changes when not in production
		!production && livereload('src/svelte'),

		// If we're building for production (npm run build
		// instead of npm run dev), minify
		production && terser()
	],
	watch: {
		clearScreen: false
	}
};
