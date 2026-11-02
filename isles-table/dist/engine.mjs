export class RustEngine {
 constructor(instance){this.wasm=instance.exports;this.encode=new TextEncoder();this.decode=new TextDecoder();}
 static async create(bytes){const {instance}=await WebAssembly.instantiate(bytes,{});return new RustEngine(instance);}
 call(message){const input=this.encode.encode(JSON.stringify(message));const p=this.wasm.alloc(input.length);let packed;try{new Uint8Array(this.wasm.memory.buffer,p,input.length).set(input);packed=this.wasm.request(p,input.length);}finally{this.wasm.dealloc(p,input.length);}const pointer=Number(packed&0xffffffffn),length=Number(packed>>32n);let text;try{text=this.decode.decode(new Uint8Array(this.wasm.memory.buffer,pointer,length));}finally{this.wasm.dealloc(pointer,length);}return JSON.parse(text);}
}
