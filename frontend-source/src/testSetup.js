import {afterEach} from 'vitest';
import {cleanup} from '@testing-library/react';
afterEach(()=>{cleanup();localStorage.clear();});
globalThis.ResizeObserver=class {observe(){}unobserve(){}disconnect(){}};
globalThis.matchMedia=()=>({matches:false,addEventListener(){},removeEventListener(){}});
