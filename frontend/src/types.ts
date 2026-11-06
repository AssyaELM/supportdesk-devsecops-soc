export type User = {id:number;name:string;email:string;role:'user'|'admin';active:boolean}
export type Ticket = {id:number;reference:string;title:string;description:string;category_id:number;category:string;priority:string;status:string;requester:User;assignee:User|null;created_at:string;updated_at:string}
export type Message = {id:number;body:string;internal:boolean;author:User;created_at:string}
export type History = {id:number;field:string;old_value:string|null;new_value:string;actor:string;created_at:string}
export type Detail = Ticket & {messages:Message[];history:History[]}
export type Category = {id:number;name:string}
export type Dashboard = {total:number;statuses:Record<string,number>;recent:Ticket[];urgent:Ticket[]}
