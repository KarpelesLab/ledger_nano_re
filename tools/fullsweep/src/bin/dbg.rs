use rawusb::hid::HidDevice;
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let ctx = rawusb::Context::new()?;
    let dev = ctx.find_device(0x2581, 0x3b7c)?.ok_or("no device")?;
    let hid = HidDevice::open(&dev)?;
    let handle = hid.handle();
    // interface 0 (the only HID interface)
    for cfg in 0u8..=0 {
        let _ = cfg;
    }
    // read the interface descriptor's endpoints
    let dev_desc = handle.device().device_descriptor();
    let _ = dev_desc;
    // use rawusb's InterfaceDescriptor via class helpers
    if let Ok(all) = rawusb::hid::interfaces(handle.device()) {
        for iface in &all {
            for e in &iface.endpoints {
                eprintln!("ep addr={:02x} attr={:02x} maxpacket={}", e.address, e.attributes, e.max_packet_size);
            }
        }
    }
    Ok(())
}
