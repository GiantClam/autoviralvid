import React from 'react';
import VideoTemplate, { VideoTemplateProps } from '../VideoTemplate';

export default function TechUnbox(props: VideoTemplateProps) {
  return (
    <VideoTemplate
      {...props}
      transition="slide"
      style={{
        ...props.style,
        primaryColor: '#00D4FF',
        secondaryColor: '#7B2FFF',
        titleFontSize: 52,
      }}
    />
  );
}
